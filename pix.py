import os
import sys
import png
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QImageReader, QPixmap, QAction, QTransform, QImage
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QLabel, QFileDialog, QScrollArea, QVBoxLayout, QTextEdit, QPushButton, QDialog, QTextBrowser
from PIL import Image, ImageQt
from PIL.ExifTags import TAGS
from cyheifloader import cyheif
import pyheif
import pyexiv2
import functools

print("Starting script", file=sys.stderr)

class DraggableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.parent = parent

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton or event.button() == Qt.RightButton:
            label_width = self.width()
            click_pos_x = event.position().x()

            if click_pos_x < 100:  # Clicked on the left side
                self.parent.navigate_images(-1)
            elif click_pos_x > label_width - 100:  # Clicked on the right side
                self.parent.navigate_images(1)
            else:  # Clicked in the middle
                pass

    def mouseDoubleClickEvent(self, event):
        self.parent.mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            image_path = urls[0].toLocalFile()
            self.parent.load_folder_images(image_path)
            self.parent.display_current_image()

class ImageViewer(QMainWindow):
    def __init__(self, file_path=None, *args, **kwargs):
        super(ImageViewer, self).__init__(*args, **kwargs)
        self.image_files = []
        self.current_image_index = 0
        self.current_rotation = 0 
        self.full_screen = False
        self.zoom_percentage = 100
        self.rotation_angle = 0
        self.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(self)

        self.zoom_factor = 1.0
        self.full_screen = False
        self.init_ui()
        filename = sys.argv[1] if len(sys.argv) > 1 else None
        if filename is not None:
            self.open_image(file_path=filename)
  
        #if file_path:
            #self.open_image(file_path)  # Call open_image instead of load_file

    def init_ui(self):
        print("Initializing UI", file=sys.stderr)
        self.label = DraggableLabel(self)
        self.label.setStyleSheet("background-color: #111111;")
        self.label.setAlignment(Qt.AlignCenter)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.installEventFilter(self)
        self.scroll_area.setAttribute(Qt.WA_NoMousePropagation)
        self.scroll_area.setWidget(self.label)
        self.scroll_area.setWidgetResizable(True)
        self.setCentralWidget(self.scroll_area)

        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_image)
        self.toolbar.addAction(open_action)

        save_as_action = QAction("Save As", self)
        save_as_action.triggered.connect(self.save_image_as)
        self.toolbar.addAction(save_as_action)

        close_image_action = QAction("Close", self)
        close_image_action.triggered.connect(self.close_image)
        self.toolbar.addAction(close_image_action)

        self.toolbar.addSeparator()

        zoom_100_action = QAction("100%", self)
        zoom_100_action.triggered.connect(self.zoom_100_percent)
        self.toolbar.addAction(zoom_100_action)

        zoom_in_action = QAction("+25%", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        self.toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction("-25%", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        self.toolbar.addAction(zoom_out_action)

        zoom_fit_action = QAction("Fit", self)
        zoom_fit_action.triggered.connect(functools.partial(self.adjust_image_zoom_fit, reset_zoom=True))
        self.toolbar.addAction(zoom_fit_action)

        rotate_left_action = QAction("Rotate -90", self)
        rotate_left_action.triggered.connect(lambda: self.rotate(-90))
        self.toolbar.addAction(rotate_left_action)

        rotate_right_action = QAction("Rotate 90", self)
        rotate_right_action.triggered.connect(lambda: self.rotate(90))
        self.toolbar.addAction(rotate_right_action)

        self.show_metadata_action = QAction("Show Metadata", self)
        self.show_metadata_action.triggered.connect(self.show_metadata)
        self.toolbar.addAction(self.show_metadata_action)

        self.setWindowTitle("Pixcie")
        self.setGeometry(100, 100, 800, 600)
        if self.image_files:
            self.display_current_image()

    def adjust_image_zoom_fit(self, reset_zoom=False):
        if self.label.pixmap():
            window_width, window_height = self.width() - 2, self.height() - 2
            image_width, image_height = self.label.pixmap().width(), self.label.pixmap().height()
            zoom_factor = min(window_width / image_width, window_height / image_height)

            if reset_zoom or (zoom_factor < 1 and zoom_factor != self.zoom_factor):
                if zoom_factor < 1:
                    image = self.load_image(self.image_files[self.current_image_index])
                    new_width = image.width() * zoom_factor
                    new_height = image.height() * zoom_factor
                    self.label.setPixmap(image.scaled(int(new_width), int(new_height), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.zoom_100_percent()

                self.zoom_factor = zoom_factor

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Left:
                self.navigate_images(-1)
                return True
            elif event.key() == Qt.Key_Right:
                self.navigate_images(1)
                return True
            elif event.key() == Qt.Key_Up:
                self.scroll_area.verticalScrollBar().triggerAction(QScrollBar.ScrollUp)
                return True
            elif event.key() == Qt.Key_Down:
                self.scroll_area.verticalScrollBar().triggerAction(QScrollBar.ScrollDown)
                return True
            elif event.key() == Qt.Key_Space:
                self.toggle_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        if self.isFullScreen():
            self.zoom_to_fit()
        else:
            self.display_current_image(reset_zoom=True)

    def load_folder_images(self, image_path):
        folder_path = os.path.dirname(image_path)
        self.image_files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.splitext(f)[1].lower() in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".heic"]
        ]
        self.current_image_index = self.image_files.index(image_path)

    def display_current_image(self, reset_zoom=True, zoom_factor=None, image=None):
        if not self.image_files:
            return
    
        if image is None:
            image_path = self.image_files[self.current_image_index]
            image = self.load_image(image_path)
        else:
            image_path = None
    
        if self.rotation_angle != 0:
            transform = QTransform().rotate(self.rotation_angle)
            image = image.transformed(transform, Qt.SmoothTransformation)
        
        image, zoom_factor = self.adjust_image_zoom_fit(image, reset_zoom=reset_zoom)
        self.zoom_percentage = int(zoom_factor * 100)
        if zoom_factor:
            self.zoom_factor = zoom_factor

        self.label.setPixmap(image)
    
        if image_path:
            self.setWindowTitle(f"{os.path.basename(image_path)} - {self.zoom_percentage}% - Pixcie")

    def load_image(self, image_path):
        try:
            if image_path.lower().endswith('.heic'):
                heif_file = pyheif.read(image_path)
                image = Image.frombytes(
                        heif_file.mode,
                        heif_file.size,
                        heif_file.data,
                        "raw",
                        heif_file.mode,
                )
                return QPixmap.fromImage(ImageQt.ImageQt(image))
            else:
                return QPixmap(image_path)
        except Exception as e:
            print(f"Error loading image: {e}")
            return QPixmap()

    def adjust_image_zoom_fit(self, image=None, reset_zoom=False):
        if image is None:
            image = self.label.pixmap()

        if not image:
            return None, 1

        window_width = self.scroll_area.width()
        window_height = self.scroll_area.height()

        image_width = image.width()
        image_height = image.height()

        zoom_width = window_width / image_width
        zoom_height = window_height / image_height

        if reset_zoom or (zoom_width < 1 and zoom_height < 1):
            zoom_factor = min(zoom_width, zoom_height)
        else:
            zoom_factor = self.zoom_percentage / 100

        new_width = int(image_width * zoom_factor)
        new_height = int(image_height * zoom_factor)

        scaled_image = image.scaled(
            new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        return scaled_image, zoom_factor

    def navigate_images(self, step):
        if self.image_files:
            new_index = (self.current_image_index + step) % len(self.image_files)
            self.current_image_index = new_index
            self.display_current_image()

    def open_image(self, file_path=None):
        if not file_path:
            options = QFileDialog.Options()
            options |= QFileDialog.ReadOnly
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Image",
                "",
                "Images (*.png *.PNG *.jpg *.JPG *.bmp *.BMP *.gif *.GIF *.jpeg *.JPEG *.heic *.HEIC);;All Files (*)",
                options=options,
            )
        if file_path:
            self.load_folder_images(file_path)
            self.display_current_image()

    def save_image_as(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image As",
            "",
            "Images (*.png *.jpg *.bmp *.gif *.heic);;All Files (*)",
            options=options,
        )
        if file_name:
            current_pixmap = self.label.pixmap()
            current_pixmap.save(file_name)

    def close_image(self):
        self.label.clear()
        self.current_image_index = -1
        self.image_files = []

    def zoom_100_percent(self):
        if self.label.pixmap():
            self.zoom_factor = 1.0
            self.update_image_zoom()

    def zoom_in(self):
        if self.label.pixmap():
            self.zoom_factor += 0.25
            self.update_image_zoom()

    def zoom_out(self):
        if self.label.pixmap():
            self.zoom_factor -= 0.25
            self.update_image_zoom()

    def zoom_to_fit(self, image=None):
        window_width, window_height = self.width(), self.height()

        if not image:
            image = self.load_image(self.image_files[self.current_image_index])

        image_width, image_height = image.width(), image.height()
        zoom_factor = min(window_width / image_width, window_height / image_height)
        self.display_current_image(reset_zoom=False, zoom_factor=zoom_factor)

    def update_image_zoom(self):
        self.zoom_factor = max(0.25, self.zoom_factor)
        pixmap = self.load_image(self.image_files[self.current_image_index])
        if pixmap:
            new_width = pixmap.width() * self.zoom_factor
            new_height = pixmap.height() * self.zoom_factor
            self.label.setPixmap(pixmap.scaled(int(new_width), int(new_height), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def extract_text_chunk(self, png_path):
        # Open the file in binary mode
        with open(png_path, 'rb') as file:
            content = file.read()

        # Look for the beginning and the end of the 'tEXt' chunk
        begin = content.find(b'tEXtparameters\00')  # the tEXt keyword you mentioned
        end = content.find(b'IDAT')  # standard keyword signaling the start of the image data

        if begin == -1 or end == -1:
            print('Could not find the text chunk in the file')
            return ''

        # Extract the chunk and decode it to a string
        text_chunk = content[begin + 15:end]  # 15 is the length of 'tEXtparameters\00'
        decoded_text = text_chunk.decode('latin-1')  # 'latin-1' encoding ensures all bytes are preserved in the resulting string
    
        # Remove non-ascii characters at the end of the string
        cleaned_text = "".join(c for c in decoded_text if 32 <= ord(c) <= 126)

        return cleaned_text

    def show_metadata(self):
        if self.image_files:
            image_path = self.image_files[self.current_image_index]
        
            # Extract additional file information
            image_info = QImageReader(image_path)
            dimensions = f"Dimensions: {image_info.size().width()} x {image_info.size().height()}"
            file_size = f"File size: {os.path.getsize(image_path)} bytes"
            folder = f"Folder: {os.path.dirname(image_path)}"

            # Construct the initial dialog text
            dialog_text = f"{dimensions}\n{file_size}\n{folder}\n\n"


            metadata = "No metadata found"
            if image_path.lower().endswith(".heic"):
                exif = cyheif.get_exif_data(image_path.encode())
                exif_readable = {TAGS.get(k):v for (k, v) in exif.items()}
                if exif_readable:
                    metadata = "\n".join(f"{k}: {v}" for k, v in exif_readable.items())

            elif image_path.lower().endswith(".png"):
                metadata = self.extract_text_chunk(image_path)
                if not metadata:
                    metadata = "No metadata found"

            else:
                with Image.open(image_path) as img:
                    exif_data = img._getexif()
                    if exif_data is not None:
                        # Convert the exif_data dict to a string
                        metadata = "\n".join(f"{k}: {v}" for k, v in exif_data.items())
        
            # Append the metadata to dialog_text
            dialog_text += metadata

            # Display the metadata dialog
            self.metadata_dialog = MetadataDialog(self, dialog_text, metadata)
            self.metadata_dialog.show()
            
    def keyPressEvent(self, event):
        image_fits_horizontally = self.label.pixmap().width() <= self.scroll_area.width()
        image_fits_vertically = self.label.pixmap().height() <= self.scroll_area.height()

        if event.key() == Qt.Key_Left:
            if image_fits_horizontally and image_fits_vertically:
                self.navigate_images(-1)
            else:
                self.scroll_area.horizontalScrollBar().triggerAction(QScrollBar.ScrollLeft)
        elif event.key() == Qt.Key_Right:
            if image_fits_horizontally and image_fits_vertically:
                self.navigate_images(1)
            else:
                self.scroll_area.horizontalScrollBar().triggerAction(QScrollBar.ScrollRight)
        elif event.key() == Qt.Key_Up:
            self.scroll_area.verticalScrollBar().triggerAction(QScrollBar.ScrollUp)
        elif event.key() == Qt.Key_Down:
            self.scroll_area.verticalScrollBar().triggerAction(QScrollBar.ScrollDown)
        elif event.key() == Qt.Key_Space:
             self.toggle_fullscreen()
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_fullscreen()

    def rotate(self, angle):
        if self.image_files:
            # Only load image if it's not already loaded
            if not hasattr(self, 'original_image'):
                image_path = self.image_files[self.current_image_index]
                self.original_image = self.load_image(image_path)  # save the original image

            # Rotate the original image by the new total rotation
            self.current_rotation = (self.current_rotation + angle) % 360  # use modulus to keep rotation between 0 and 359
            pil_image = self.original_image.toImage().convertToFormat(QImage.Format_RGB888)
            pil_image = pil_image.mirrored(False, True)  # Flip vertically (optional)
            
            transform = QTransform().rotate(float(self.current_rotation))
            rotated_image = pil_image.transformed(transform, Qt.SmoothTransformation)

            # Convert back to QPixmap
            image = QPixmap.fromImage(rotated_image)

            self.display_current_image(reset_zoom=False, zoom_factor=self.zoom_factor, image=image)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.toolbar.show()  # Show the toolbar when returning to normal mode
        else:
            self.showFullScreen()
            self.toolbar.hide()  # Hide the toolbar in full-screen mode

class MetadataDialog(QDialog):
    def __init__(self, parent=None, dialog_text=None, metadata=None):
        super().__init__(parent)
        self.setWindowTitle("Image Metadata")
        self.setFixedSize(600, 400)
        layout = QVBoxLayout()
        self.text_browser = QTextBrowser()
        self.text_browser.setText(dialog_text)
        layout.addWidget(self.text_browser)

        # Button to copy metadata to clipboard
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(lambda: self.copy_to_clipboard_and_close(metadata))
        layout.addWidget(copy_button)

        self.setLayout(layout)

    def copy_to_clipboard_and_close(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.close()

def main():
    app = QApplication(sys.argv)
    filename = sys.argv[1] if len(sys.argv) > 1 else None
    viewer = ImageViewer(file_path=filename)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
    print("Entering main", file=sys.stderr)
