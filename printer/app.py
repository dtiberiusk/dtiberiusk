"""
Simple print service for dtiberiusk.com

Any page on the site can send a file to   POST /printer/api/print   and it gets printed.

  Form fields:
    file    (required)  the file to print: PDF, JPG, PNG or TXT, up to 25 MB
    copies  (optional)  1-20, default 1
    duplex  (optional)  "1" for two-sided
    pages   (optional)  e.g. "1-3,5"  (PDFs)

  Answers with JSON:  {"ok": true, "job": "HLL2460DW-7"}   or   {"ok": false, "error": "..."}

It prints to the server's default printer (set with: sudo lpadmin -d HLL2460DW).
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

    if request.form.get("duplex") == "1":
        cmd += ["-o", "sides=two-sided-long-edge"]

    pages = request.form.get("pages", "").replace(" ", "")
    if pages:
        if not PAGES.match(pages):
            return fail("Pages should look like 1-3,5")
        cmd += ["-P", pages]

    if ext != ".txt" and ext != ".pdf":
        cmd += ["-o", "fit-to-page"]                            # scale photos to the page

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
