import sys
import os # For file extension check
from PySide6.QtWidgets import QWidget, QApplication, QSizePolicy, QMessageBox
from PySide6.QtCore import Qt, QRect, QSize, QPoint, Signal, QRectF, QMimeData, QUrl
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QFont, 
    QRadialGradient, QFontMetrics, QDragEnterEvent, QDropEvent, QMouseEvent, QDragLeaveEvent, QDragMoveEvent,
    QPaintEvent, QWheelEvent, QKeyEvent # Import QWheelEvent and QKeyEvent
)
import pretty_midi
import math # Import math

from config.constants import (
    MIN_PITCH, MAX_PITCH, WHITE_KEY_WIDTH, BLACK_KEY_WIDTH,
    WHITE_KEY_HEIGHT, BLACK_KEY_HEIGHT, BASE_TIME_SCALE, DEFAULT_BPM,
    MIN_LABEL_PITCH, MAX_LABEL_PITCH
)
from config.theme import (
    PIANO_ROLL_BG_COLOR, GRID_LINE_COLOR, GRID_BEAT_LINE_COLOR, GRID_MEASURE_LINE_COLOR, # Updated specific grid colors
    GRID_ROW_HIGHLIGHT_COLOR, KEY_GRID_LINE_COLOR, PLAYHEAD_COLOR, PIANO_KEY_WHITE_COLOR, PIANO_KEY_BLACK_COLOR, 
    PIANO_KEY_BORDER_COLOR, NOTE_LOW_COLOR, NOTE_MED_COLOR, NOTE_HIGH_COLOR, NOTE_BORDER_COLOR, # Updated specific note and key colors
    ACCENT_PRIMARY_COLOR, DRAG_OVERLAY_COLOR # Updated general theme colors
)
from ui.drawing_utils import (
    draw_time_grid, draw_piano_keys, draw_notes, draw_playhead
)
from config import theme

class PianoRollDisplay(QWidget):
    """Widget that displays MIDI notes in a piano roll format"""
    
    notesChanged = Signal(list) 
    midiFileProcessed = Signal(list) 

    MIN_HORIZONTAL_ZOOM = 0.1
    MAX_HORIZONTAL_ZOOM = 10.0
    MIN_VERTICAL_ZOOM = 0.25
    MAX_VERTICAL_ZOOM = 4.0

    def __init__(self, notes=None, parent=None):
        super().__init__(parent)
        self.notes: list[pretty_midi.Note] = notes or []
        self.playhead_position = 0.0
        self.bpm = DEFAULT_BPM
        self.horizontal_zoom_factor = 1.0
        self.vertical_zoom_factor = 1.0
        # Initialize time_scale without BPM dependency
        self.time_scale = BASE_TIME_SCALE * self.horizontal_zoom_factor
        self.time_signature_numerator = 4
        self.time_signature_denominator = 4
        
        num_white_keys = 0
        for i in range(MIN_PITCH, MAX_PITCH + 1):
            if i % 12 not in [1, 3, 6, 8, 10]: 
                num_white_keys +=1
        self.setMinimumHeight(int((MAX_PITCH - MIN_PITCH + 1) * WHITE_KEY_HEIGHT * self.vertical_zoom_factor))

        
        self.calculate_total_width()
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAcceptDrops(True) 
        self._is_dragging_midi = False 
        self._grid_quantize_value_seconds = (60.0 / self.bpm) / 4
        self.setFocusPolicy(Qt.StrongFocus) # Ensure widget can receive key events


    def _update_quantization_value(self):
        beats_per_second = self.bpm / 60.0
        seconds_per_beat = 1.0 / beats_per_second
        self._grid_quantize_value_seconds = seconds_per_beat / 4.0

    def set_notes(self, notes: list[pretty_midi.Note]):
        self.notes = notes if notes is not None else []
        self.calculate_total_width()
        self.notesChanged.emit(self.notes) 
        self.update()

    def add_note(self, note: pretty_midi.Note, emit_change=True): # Kept for programmatic addition
        if not isinstance(note, pretty_midi.Note):
            print(f"PianoRollDisplay: Received invalid note object type: {type(note)}")
            return
        self.notes.append(note)
        self.notes.sort(key=lambda n: (n.start, n.pitch))
        original_min_width = self.minimumWidth()
        self.calculate_total_width()
        if emit_change:
            self.notesChanged.emit(self.notes)
        self.update()
        parent_scroll_area = self.parentWidget()
        while parent_scroll_area and not hasattr(parent_scroll_area, 'horizontalScrollBar'):
            parent_scroll_area = parent_scroll_area.parentWidget()
        if parent_scroll_area and hasattr(parent_scroll_area, 'horizontalScrollBar'):
            note_x_end_pixels = note.end * self.time_scale + WHITE_KEY_WIDTH
            scrollbar = parent_scroll_area.horizontalScrollBar()
            if note_x_end_pixels > scrollbar.value() + parent_scroll_area.viewport().width() or self.minimumWidth() > original_min_width:
                scrollbar.setValue(int(note.start * self.time_scale))
    
    # Removed delete_note_at as per feedback

    def set_playhead_position(self, position):
        if self.playhead_position != position:
            self.playhead_position = position
            self.update() 
    
    def set_bpm(self, bpm):
        if bpm <= 0 or self.bpm == bpm: return
        self.bpm = bpm
        # self.time_scale = BASE_TIME_SCALE * (DEFAULT_BPM / self.bpm) * self.horizontal_zoom_factor # REMOVED as per task
        self._update_quantization_value() # This depends on BPM, so it's correct here
        self.calculate_total_width() # This might implicitly use BPM for min_time_from_bars, ensure it's still logical
        self.update() # Redraw the display (grid lines will change based on new BPM)

    def set_time_signature(self, numerator: int, denominator: int):
        if numerator <= 0 or denominator <= 0: return
        if self.time_signature_numerator == numerator and self.time_signature_denominator == denominator: return
        self.time_signature_numerator = numerator
        self.time_signature_denominator = denominator
        self._update_quantization_value()
        self.calculate_total_width()
        self.update()
    
    def calculate_total_width(self):
        max_time = 0.0
        if self.notes:
            for note in self.notes:
                if hasattr(note, 'end') and note.end > max_time:
                    max_time = note.end
        min_visible_bars = 4
        min_time_from_bars = min_visible_bars * self.time_signature_numerator * (60.0 / self.bpm)
        self.total_time = max(max_time + 2.0, min_time_from_bars)
        new_min_width = int(self.total_time * self.time_scale) + WHITE_KEY_WIDTH
        if self.minimumWidth() != new_min_width:
            self.setMinimumWidth(new_min_width)
            self.updateGeometry()

    def sizeHint(self):
        num_white_keys = 0
        for i in range(MIN_PITCH, MAX_PITCH + 1):
            if i % 12 not in [1, 3, 6, 8, 10]:
                num_white_keys +=1
        effective_white_key_height = WHITE_KEY_HEIGHT * self.vertical_zoom_factor
        return QSize(self.minimumWidth(), int(num_white_keys * effective_white_key_height))
    
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        
        # Use solid PIANO_ROLL_BG_COLOR
        painter.fillRect(event.rect(), theme.PIANO_ROLL_BG_COLOR)

        # Draw drag overlay BEFORE notes to prevent pink glitch
        if self._is_dragging_midi:
            painter.save()
            # Use the dedicated theme color for drag overlay
            painter.fillRect(self.rect().adjusted(WHITE_KEY_WIDTH + 1, 1, -1, -1), theme.DRAG_OVERLAY_COLOR)
            
            # Keep the border distinct
            border_pen = QPen(theme.ACCENT_PRIMARY_COLOR.lighter(130), 2, Qt.DashLine) # Use ACCENT_PRIMARY_COLOR
            painter.setPen(border_pen)
            painter.drawRect(self.rect().adjusted(WHITE_KEY_WIDTH + 1, 1, -1, -1))
            painter.restore()

        # Draw regular UI elements after the overlay
        draw_time_grid(painter, self.width(), self.height(), self.time_scale, self.bpm,
                       self.time_signature_numerator, self.time_signature_denominator, 
                       self.parentWidget(), self.vertical_zoom_factor)
        draw_piano_keys(painter, self.vertical_zoom_factor) 
        draw_notes(painter, self.notes, self.time_scale, self.vertical_zoom_factor) 
        draw_playhead(painter, self.playhead_position, self.time_scale, self.height())

    def _pixel_to_time(self, x_pos: int) -> float:
        if x_pos <= WHITE_KEY_WIDTH: return 0.0
        return (x_pos - WHITE_KEY_WIDTH) / self.time_scale

    def _pixel_to_pitch(self, y_pos: int) -> int:
        effective_white_key_height = WHITE_KEY_HEIGHT * self.vertical_zoom_factor
        if effective_white_key_height <= 0: return MIN_PITCH
        # Calculate pitch index from the top. Each key slot (white or black) effectively occupies `effective_white_key_height` vertically.
        # The y_pos is relative to the start of the piano roll content.
        pitch_offset = math.floor(y_pos / effective_white_key_height)
        # Convert this offset to an actual MIDI pitch number (higher y means lower pitch)
        pitch = MAX_PITCH - pitch_offset
        return max(MIN_PITCH, min(MAX_PITCH, pitch))

    def _pitch_to_pixel_y(self, pitch: int) -> float:
        effective_white_key_height = WHITE_KEY_HEIGHT * self.vertical_zoom_factor
        # Calculate y position from the top for a given pitch
        # Higher pitch means smaller y value
        y_pos = (MAX_PITCH - pitch) * effective_white_key_height
        return y_pos

    def _quantize_time(self, time_sec: float) -> float:
        if self._grid_quantize_value_seconds <= 0: return time_sec
        return round(time_sec / self._grid_quantize_value_seconds) * self._grid_quantize_value_seconds

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.x() > WHITE_KEY_WIDTH:
            pos_x = int(event.position().x())
            clicked_time_raw = self._pixel_to_time(pos_x)
            self.playhead_position = clicked_time_raw
            # If MainWindow needs to know about manual playhead changes to sync TransportControls:
            # self.notesChanged.emit(self.notes) # Or a dedicated signal
            self.update() 
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        super().mouseDoubleClickEvent(event) # No custom double-click action

    def dragEnterEvent(self, event: QDragEnterEvent):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            urls = mime_data.urls()
            if urls and urls[0].isLocalFile():
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith(('.mid', '.midi')):
                    event.acceptProposedAction()
                    self._is_dragging_midi = True
                    self.update()
                    return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if self._is_dragging_midi: event.acceptProposedAction()
        else: event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._is_dragging_midi = False
        self.update()
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self._is_dragging_midi = False
        self.update() # Clear drag feedback immediately
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.mid', '.midi')):
                    try:
                        midi_data = pretty_midi.PrettyMIDI(file_path)
                        if midi_data.instruments:
                            all_notes = []
                            for instrument in midi_data.instruments:
                                all_notes.extend(instrument.notes)
                            all_notes.sort(key=lambda x: x.start)
                            
                            # Update internal notes and repaint PianoRollDisplay first
                            self.set_notes(all_notes) # This calls self.update() and emits notesChanged
                            
                            # midiFileProcessed can still be used if MainWindow needs a distinct signal for "file loaded"
                            # vs. "notes changed by any means". If notesChanged is sufficient, this can be removed.
                            # For now, let's assume MainWindow might want to differentiate.
                            self.midiFileProcessed.emit(all_notes) # Emitting with the same notes set
                            
                            event.acceptProposedAction()
                        else:
                            QMessageBox.warning(self, "MIDI Parse Error", "No instruments found in MIDI file.")
                            event.ignore()
                    except Exception as e:
                        print(f"Error parsing MIDI file {file_path}: {e}")
                        QMessageBox.critical(self, "MIDI Parse Error", f"Could not parse MIDI file:\n{e}")
                        event.ignore()
                    return # Processed or ignored
        event.ignore()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.ControlModifier:
            mouse_x = event.position().x()

            if mouse_x <= WHITE_KEY_WIDTH:
                # Ignore zoom if cursor is over piano keys for horizontal zoom
                # but allow vertical zoom or other handling by parent
                super().wheelEvent(event)
                return

            old_scroll_x = 0
            parent_scroll_area = self.parentWidget()
            while parent_scroll_area and not hasattr(parent_scroll_area, 'horizontalScrollBar'):
                parent_scroll_area = parent_scroll_area.parentWidget()
            
            if parent_scroll_area and hasattr(parent_scroll_area, 'horizontalScrollBar'):
                old_scroll_x = parent_scroll_area.horizontalScrollBar().value()

            # Time at cursor before zoom (absolute time)
            time_at_cursor = self._pixel_to_time(mouse_x + old_scroll_x)

            delta = event.angleDelta().y()
            zoom_speed_factor = 1.1

            if delta > 0:  # Zoom in
                new_zoom_factor = self.horizontal_zoom_factor * zoom_speed_factor
            elif delta < 0:  # Zoom out
                new_zoom_factor = self.horizontal_zoom_factor / zoom_speed_factor
            else: # No change
                event.accept()
                return

            self.horizontal_zoom_factor = max(self.MIN_HORIZONTAL_ZOOM, min(self.MAX_HORIZONTAL_ZOOM, new_zoom_factor))
            
            # Update time_scale without BPM dependency
            self.time_scale = BASE_TIME_SCALE * self.horizontal_zoom_factor
            
            # This recalculates minimum width based on new time_scale and total_time
            self.calculate_total_width() 

            # New pixel X for the time_at_cursor with the new time_scale (relative to grid start)
            new_pixel_x_for_time_at_cursor = time_at_cursor * self.time_scale
            
            # Calculate new scrollbar value to keep time_at_cursor under the mouse
            # mouse_x is relative to widget, WHITE_KEY_WIDTH is offset of grid from widget start
            new_scroll_x = new_pixel_x_for_time_at_cursor - (mouse_x - WHITE_KEY_WIDTH)
            
            if parent_scroll_area and hasattr(parent_scroll_area, 'horizontalScrollBar'):
                parent_scroll_area.horizontalScrollBar().setValue(int(new_scroll_x))
            
            self.update() # Redraw with new zoom and scroll
            event.accept()
        elif event.modifiers() == Qt.ShiftModifier: # Vertical zoom
            mouse_y = event.position().y()
            old_scroll_y = 0
            parent_scroll_area = self.parentWidget()
            while parent_scroll_area and not hasattr(parent_scroll_area, 'verticalScrollBar'):
                parent_scroll_area = parent_scroll_area.parentWidget()
            
            if parent_scroll_area and hasattr(parent_scroll_area, 'verticalScrollBar'):
                old_scroll_y = parent_scroll_area.verticalScrollBar().value()

            pitch_at_cursor = self._pixel_to_pitch(mouse_y + old_scroll_y)

            delta = event.angleDelta().y()
            zoom_speed_factor = 1.1

            if delta > 0:  # Zoom in
                new_zoom_factor = self.vertical_zoom_factor * zoom_speed_factor
            elif delta < 0:  # Zoom out
                new_zoom_factor = self.vertical_zoom_factor / zoom_speed_factor
            else: # No change
                event.accept()
                return
            
            self.vertical_zoom_factor = max(self.MIN_VERTICAL_ZOOM, min(self.MAX_VERTICAL_ZOOM, new_zoom_factor))
            
            new_min_height = int((MAX_PITCH - MIN_PITCH + 1) * WHITE_KEY_HEIGHT * self.vertical_zoom_factor)
            self.setMinimumHeight(new_min_height)

            new_pixel_y_for_pitch_at_cursor = self._pitch_to_pixel_y(pitch_at_cursor)
            new_scroll_y = new_pixel_y_for_pitch_at_cursor - mouse_y
            
            if parent_scroll_area and hasattr(parent_scroll_area, 'verticalScrollBar'):
                parent_scroll_area.verticalScrollBar().setValue(int(new_scroll_y))
            
            self.update()
            event.accept()
        else:
            super().wheelEvent(event) # Default handling for other cases (e.g. vertical scroll)

    def _zoom_horizontal_to_center(self, zoom_factor_change_multiplier: float):
        parent_scroll_area = self.parentWidget()
        while parent_scroll_area and not hasattr(parent_scroll_area, 'horizontalScrollBar'):
            parent_scroll_area = parent_scroll_area.parentWidget()

        current_scroll_x = 0
        current_viewport_center_x_widget_relative = self.width() / 2 # Fallback if no scrollbar

        if parent_scroll_area and hasattr(parent_scroll_area, 'horizontalScrollBar'):
            scrollbar = parent_scroll_area.horizontalScrollBar()
            viewport_width = parent_scroll_area.viewport().width()
            current_scroll_x = scrollbar.value()
            # Center of the viewport in viewport coordinates (relative to viewport start)
            current_viewport_center_x_widget_relative = viewport_width / 2
        
        # Time at the center of the viewport (absolute time)
        time_at_center = self._pixel_to_time(current_viewport_center_x_widget_relative + current_scroll_x)

        old_horizontal_zoom_factor = self.horizontal_zoom_factor
        new_horizontal_zoom_factor = old_horizontal_zoom_factor * zoom_factor_change_multiplier
        
        self.horizontal_zoom_factor = max(self.MIN_HORIZONTAL_ZOOM, min(self.MAX_HORIZONTAL_ZOOM, new_horizontal_zoom_factor))
        
        # Update time_scale based on the new zoom factor, without BPM dependency
        self.time_scale = BASE_TIME_SCALE * self.horizontal_zoom_factor
        
        # Recalculate total width which also calls updateGeometry
        self.calculate_total_width() 

        # New pixel X for the time_at_center with the new time_scale (relative to grid start)
        new_pixel_x_for_time_at_center = time_at_center * self.time_scale
        
        # Calculate new scrollbar value
        # current_viewport_center_x_widget_relative is the offset from the start of the viewport to its center
        new_scroll_x = new_pixel_x_for_time_at_center - current_viewport_center_x_widget_relative
        
        if parent_scroll_area and hasattr(parent_scroll_area, 'horizontalScrollBar'):
            parent_scroll_area.horizontalScrollBar().setValue(int(new_scroll_x))
            
        self.update()


    def keyPressEvent(self, event: QKeyEvent):
        zoom_speed_factor = 1.2 # Can be different from wheel zoom
        if event.modifiers() == Qt.ControlModifier and not event.modifiers() & Qt.ShiftModifier: # Ctrl only
            if event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal: 
                self._zoom_horizontal_to_center(zoom_speed_factor)
                event.accept()
            elif event.key() == Qt.Key_Minus:
                self._zoom_horizontal_to_center(1 / zoom_speed_factor)
                event.accept()
            else:
                super().keyPressEvent(event)
        elif event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier): # Ctrl + Shift
            if event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:
                self._zoom_vertical_to_center(zoom_speed_factor)
                event.accept()
            elif event.key() == Qt.Key_Minus:
                self._zoom_vertical_to_center(1 / zoom_speed_factor)
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _zoom_vertical_to_center(self, zoom_factor_change_multiplier: float):
        parent_scroll_area = self.parentWidget()
        while parent_scroll_area and not hasattr(parent_scroll_area, 'verticalScrollBar'):
            parent_scroll_area = parent_scroll_area.parentWidget()

        current_scroll_y = 0
        current_viewport_center_y_widget_relative = self.height() / 2 # Fallback

        if parent_scroll_area and hasattr(parent_scroll_area, 'verticalScrollBar'):
            scrollbar = parent_scroll_area.verticalScrollBar()
            viewport_height = parent_scroll_area.viewport().height()
            current_scroll_y = scrollbar.value()
            current_viewport_center_y_widget_relative = viewport_height / 2
        
        pitch_at_center = self._pixel_to_pitch(current_viewport_center_y_widget_relative + current_scroll_y)
        
        old_vertical_zoom_factor = self.vertical_zoom_factor
        new_vertical_zoom_factor = old_vertical_zoom_factor * zoom_factor_change_multiplier
        
        self.vertical_zoom_factor = max(self.MIN_VERTICAL_ZOOM, min(self.MAX_VERTICAL_ZOOM, new_vertical_zoom_factor))
        
        new_min_height = int((MAX_PITCH - MIN_PITCH + 1) * WHITE_KEY_HEIGHT * self.vertical_zoom_factor)
        self.setMinimumHeight(new_min_height)

        new_pixel_y_for_pitch_at_center = self._pitch_to_pixel_y(pitch_at_center)
        new_scroll_y = new_pixel_y_for_pitch_at_center - current_viewport_center_y_widget_relative
        
        if parent_scroll_area and hasattr(parent_scroll_area, 'verticalScrollBar'):
            parent_scroll_area.verticalScrollBar().setValue(int(new_scroll_y))
            
        self.update()