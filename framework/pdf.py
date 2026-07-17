"""
HTML -> PDF with engine fallback.

Engines, tried in the order configured under settings `pdf.engines`:
    wkhtmltopdf   what production hosts have; pixel-exact with the 718px grid
    chrome        headless Chrome/Chromium --print-to-pdf (dev machines)
    weasyprint    pure-python fallback when installed

PDF failure never kills a run - the HTML artifact is always written first
and the failure is reported as a warning.
"""
import os
import shutil
import subprocess


class PDFError(Exception):
    pass


def _find(candidates):
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    return None


def _wkhtmltopdf(html_file, pdf_file, cfg, footer_left):
    binary = cfg.get("wkhtmltopdf_path") or _find(["wkhtmltopdf"])
    if not binary:
        raise PDFError("wkhtmltopdf not found")
    # --disable-smart-shrinking + --dpi 96 make 1 CSS px == 1/96in, which the
    # 718px page grid in base.html assumes.
    cmd = [
        binary, "--quiet",
        "--enable-local-file-access",
        "--page-size", "A4", "--encoding", "UTF-8",
        "--dpi", "96", "--image-quality", "100",
        "--disable-smart-shrinking", "--print-media-type",
        "--margin-top", "10mm", "--margin-bottom", "12mm",
        "--margin-left", "10mm", "--margin-right", "10mm",
        "--footer-font-name", "Arial", "--footer-font-size", "7",
        "--footer-spacing", "4",
        "--footer-left", footer_left,
        "--footer-right", "Page [page] of [topage]",
        html_file, pdf_file,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0 or not os.path.exists(pdf_file):
        raise PDFError(f"wkhtmltopdf failed: {res.stderr.strip()[:400]}")


def _chrome(html_file, pdf_file, cfg, footer_left):
    binary = cfg.get("chrome_path") or _find(
        ["google-chrome", "google-chrome-stable", "chromium",
         "chromium-browser"])
    if not binary:
        raise PDFError("chrome/chromium not found")
    cmd = [
        binary, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_file}",
        "file://" + os.path.abspath(html_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not os.path.exists(pdf_file):
        raise PDFError(f"chrome failed: {res.stderr.strip()[:400]}")


def _weasyprint(html_file, pdf_file, cfg, footer_left):
    try:
        from weasyprint import HTML
    except ImportError as e:
        raise PDFError("weasyprint not installed") from e
    HTML(filename=html_file).write_pdf(pdf_file)


ENGINES = {
    "wkhtmltopdf": _wkhtmltopdf,
    "chrome": _chrome,
    "weasyprint": _weasyprint,
}


def html_to_pdf(html_file, pdf_file, pdf_settings, footer_left=""):
    """Returns the engine used. Raises PDFError when every engine failed."""
    errors = []
    for name in pdf_settings.get("engines", ["wkhtmltopdf", "chrome",
                                             "weasyprint"]):
        fn = ENGINES.get(name)
        if fn is None:
            errors.append(f"{name}: unknown engine")
            continue
        try:
            fn(html_file, pdf_file, pdf_settings, footer_left)
            return name
        except (PDFError, subprocess.TimeoutExpired) as e:
            errors.append(f"{name}: {e}")
    raise PDFError("; ".join(errors))
