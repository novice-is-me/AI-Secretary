from PIL import Image
import pytesseract
import io


def extract_text_from_image(image_file) -> str:
    image = Image.open(image_file)
    text = pytesseract.image_to_string(image)
    return text.strip()
