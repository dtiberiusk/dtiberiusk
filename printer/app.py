"""
Simple print service for dtiberiusk.com

Any page on the site can send a file to   POST /printer/api/print   and it gets printed.

  Form fields:
    file    (required)  the file to print: PDF, JPG, PNG or TXT, up to 25 MB
    copies  (optional)  1-20, default 1
    duplex  (optional)  "1" for two-sided
    pages   (optional)  e.g. "1-3,5"  (PDFs)
    media   (optional)  paper size: "letter", "legal", "a4", or WxH in inches, e.g. "6x8"
                        (width 3-8.5, height 5-14, width <= height). Default: the printer's default.
                        Two-sided printing is only allowed on letter, legal and a4.

  The print page (printer/index.html) scales and centers everything onto the chosen paper size in the
  browser and always sends a PDF whose pages already match "media", so nothing gets rescaled here.

  Answers with JSON:  {"ok": true, "job": "HLL2460DW-7"}   or   {"ok": false, "error": "..."}

It prints to the
 server's default printer (set with: sudo lpadmin -d HLL2460DW).
It only listens on 127.0.0.1:5000. Caddy puts the password in front of it.
"""
import os
import re
import subprocess
import tempfile

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024          # 25 MB

ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".txt"}
PAGES = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")              # 1-3,5
CUSTOM = re.compile(r"^(\d+(?:\.\d{1,2})?)x(\d+(?:\.\d{1,2})?)$")    # 6x8, 8.5x11
NAMED = {"letter": "Letter", "legal": "Legal", "a4": "A4"}             # sizes the printer can also duplex


def media_option(value):
    """Turn the media form field into a CUPS media name, or None if it isn't allowed."""
    value = value.strip().lower()
    if value in NAMED:
        return NAMED[value]
    m = CUSTOM.match(value)
    if not m:
        return None
    w, h = float(m.group(1)), float(m.group(2))
    if not (3 <= w <= 8.5 and 5 <= h <= 14 and w <= h):          # HL-L2460DW manual feed slot limits
        return None
    return "Custom.%gx%gin" % (w, h)


def fail(message, code=400):
    return jsonify(ok=False, error=message), code


@app.errorhandler(413)
def too_big(_):
    return fail("That file is larger than 25 MB.", 413)


@app.post("/printer/api/print")
def print_file():
    f = request.files.get("file")
    if not f or not f.filename:
        return fail("No file was sent.")

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return fail("Only PDF, JPG, PNG or TXT files can be printed.")

    # Build the print command: lp [options] file
    cmd = ["lp"]

    copies = request.form.get("copies", "1")
    if not copies.isdigit() or not 1 <= int(copies) <= 20:
        return fail("Copies must be a number from 1 to 20.")
    cmd += ["-n", copies]

    title = re.sub(r"[^\w .()-]", "_", f.filename)[:60]
    cmd += ["-t", title]

    media = request.form.get("media", "")
    if media:
        cups_media = media_option(media)
        if not cups_media:
            return fail("Paper size should be letter, legal, a4 or something like 6x8.")
        cmd += ["-o", "media=" + cups_media]

    if request.form.get("duplex") == "1":
        if media and media.strip().lower() not in NAMED:
            return fail("Two-sided printing only works on Letter, Legal and A4 paper.")
        cmd += ["-o", "sides=two-sided-long-edge"]

    pages = request.form.get("pages", "").replace(" ", "")
    if pages:
        if not PAGES.match(pages):
            return fail("Pages should look like 1-3,5")
        cmd += ["-P", pages]

    if ext != ".txt" and ext != ".pdf":
        cmd += ["-o", "fit-to-page"]                            # raw photos from other pages: scale to the page

    # Save the upload to a temporary file, print it, then delete it
    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as out:
            f.save(out)
        result = subprocess.run(cmd + [path], capture_output=True, text=True, timeout=30)
    finally:
        os.remove(path)

    if result.returncode != 0:
        return fail(result.stderr.strip() or "The printer refused the job.", 500)

    job = re.search(r"request id is (\S+)", result.stdout)     # "request id is HLL2460DW-7 (1 file(s))"
    return jsonify(ok=True, job=job.group(1) if job else None)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
