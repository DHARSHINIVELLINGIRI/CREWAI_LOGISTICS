"""
Barcode Service — generates clean Code128 barcodes for shipment tracking IDs.

Produces a large, clear barcode (bars + human-readable ID below) exactly like
a standard shipping label barcode — no extra info panels, just the barcode.
"""

import io
from typing import Optional


def generate_barcode_png(
    tracking_id: str,
    bar_width: float = 2.5,
    bar_height: float = 60.0,
    font_size: int = 14,
    quiet_zone: float = 4.0,
    text_distance: float = 5.0,
) -> Optional[bytes]:
    """
    Generate a clean Code128 barcode image for the given tracking_id.

    The output matches the standard shipping barcode style:
    - Tall, thick black bars on a white background
    - Human-readable tracking ID printed below the bars
    - Quiet zone (white margin) on all sides

    Returns PNG bytes, or None on failure.
    """
    try:
        import barcode as bc
        from barcode.writer import ImageWriter

        buf = io.BytesIO()
        writer = ImageWriter()

        options = {
            "write_text":    True,
            "module_width":  bar_width,
            "module_height": bar_height,
            "font_size":     font_size,
            "quiet_zone":    quiet_zone,
            "text_distance": text_distance,
            "background":    "white",
            "foreground":    "black",
        }

        code = bc.get("code128", tracking_id, writer=writer)
        code.write(buf, options=options)
        buf.seek(0)
        raw = buf.read()

        # Add a subtle light-grey border around the white barcode canvas
        raw = _add_border(raw, border_px=12, border_color=(230, 230, 230))
        return raw

    except Exception:
        return None


def _add_border(png_bytes: bytes, border_px: int = 12,
                border_color: tuple = (230, 230, 230)) -> bytes:
    """Wrap barcode PNG with a padded border using Pillow."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        bordered = ImageOps.expand(img, border=border_px, fill=border_color)
        buf = io.BytesIO()
        bordered.save(buf, format="PNG", dpi=(150, 150))
        buf.seek(0)
        return buf.read()
    except Exception:
        return png_bytes   # return original if Pillow unavailable


def render_barcode_section(
    st_container,
    tracking_id: str,
    source: str = "",
    destination: str = "",
    carrier: str = "",
    status: str = "",
    weight: str = "",
    priority: str = "",
    show_download: bool = True,
    compact: bool = False,
):
    """
    Render a clean Code128 barcode + download button inside any Streamlit container.

    The barcode encodes `tracking_id` exactly as shown in the reference image:
    tall thick bars on white, with the tracking ID printed below.

    Args:
        st_container : Any st.* container (st, column, expander, etc.)
        tracking_id  : Shipment tracking ID to encode in the barcode
        show_download: Whether to show an ⬇️ Download PNG button
        compact      : If True, generate a slightly smaller barcode
    """
    import streamlit as st

    if compact:
        png_bytes = generate_barcode_png(
            tracking_id,
            bar_width=1.8,
            bar_height=36.0,
            font_size=10,
            quiet_zone=3.0,
            text_distance=3.5,
        )
    else:
        png_bytes = generate_barcode_png(
            tracking_id,
            bar_width=2.5,
            bar_height=60.0,
            font_size=14,
            quiet_zone=4.0,
            text_distance=5.0,
        )

    if png_bytes is None:
        st_container.warning(
            "⚠️ Barcode generation failed — ensure `python-barcode` is installed."
        )
        return

    st_container.image(
        png_bytes,
        use_container_width=True,
    )

    if show_download:
        st_container.download_button(
            label="⬇️ Download Barcode",
            data=png_bytes,
            file_name=f"barcode_{tracking_id}.png",
            mime="image/png",
            use_container_width=True,
            key=f"dl_barcode_{tracking_id}",
        )
