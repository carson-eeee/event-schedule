import qrcode
from PIL import Image, ImageDraw
import io

def generate_qr_code(url: str, style: str, color: str = None) -> io.BytesIO:
    """Generate a QR code with the specified style and color."""
    # Default color
    fg_color = color if color else "black"
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Create base image
    if style == "solid":
        img = qr.make_image(fill_color=fg_color, back_color="white")
    else:
        # Convert to PIL image for gradient styles
        base_img = qr.make_image(fill_color="black", back_color="white")
        img = Image.new("RGB", base_img.size, "white")
        draw = ImageDraw.Draw(img)
        
        width, height = base_img.size
        for y in range(height):
            for x in range(width):
                if base_img.getpixel((x, y)) == 0:  # Black pixel (QR code)
                    if style == "horizontal_gradient":
                        r = int(255 * (x / width))
                        g = 0
                        b = int(255 * (1 - x / width))
                    elif style == "vertical_gradient":
                        r = int(255 * (y / height))
                        g = 0
                        b = int(255 * (1 - y / height))
                    elif style == "radial_gradient":
                        cx, cy = width / 2, height / 2
                        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                        max_dist = ((width / 2) ** 2 + (height / 2) ** 2) ** 0.5
                        r = int(255 * (dist / max_dist))
                        g = 0
                        b = int(255 * (1 - dist / max_dist))
                    else:
                        r, g, b = 0, 0, 0  # Fallback
                    draw.point((x, y), (r, g, b))
    
    # Override color for solid style if specified
    if style == "solid" and color:
        img = img.convert("RGB")
        pixels = img.load()
        for y in range(img.size[1]):
            for x in range(img.size[0]):
                if pixels[x, y] == (0, 0, 0):  # Black pixel
                    pixels[x, y] = Image.new("RGB", (1, 1), fg_color).getpixel((0, 0))
    
    # Save to BytesIO
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output