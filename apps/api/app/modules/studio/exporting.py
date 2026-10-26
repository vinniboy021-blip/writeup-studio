# SPDX-License-Identifier: MIT
"""Deterministic exports. Renderers never retrieve URLs from document content."""
import base64
from html import escape
from io import BytesIO
import json
import re
import zipfile

import bleach
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from app.modules.evidence.storage import read_object


MIME = {"markdown": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
        "json": "application/json", "pdf": "application/pdf"}
EXTENSION = {"markdown": "md", "html": "html", "json": "json", "pdf": "pdf"}


def _anchor(section_id):
    return "section-" + re.sub(r"[^a-zA-Z0-9_-]", "", section_id)


def _image_map(manifest):
    result = {}
    for item in manifest:
        if item["mime_type"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            continue
        data = read_object(item["storage_key"], max_bytes=20971520)
        url = "data:" + item["mime_type"] + ";base64," + base64.b64encode(data).decode("ascii")
        result[item["id"]] = {**item, "data_url": url, "bytes": data}
    return result


def _source_id(value):
    match = re.fullmatch(r"(?:evidence:|/api/v1/evidences/)([a-fA-F0-9-]{36})(?:/download)?", value)
    return match.group(1) if match else None


def sanitize_markdown(content):
    """Keep literal commands intact inside fenced/inline code; strip executable HTML."""
    parts = re.split(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)", content)
    cleaned = "".join(part if index % 2 else bleach.clean(part, tags=[], strip=True)
                   for index, part in enumerate(parts))
    # Remove unsafe link destinations while preserving the visible label.
    cleaned = re.sub(r"\\[([^]\\n]+)\\]\\((?:javascript|data):[^)]*\\)", r"\\1", cleaned, flags=re.IGNORECASE)
    return cleaned


def markdown_text(snapshot, images=None):
    images = images or {}
    pieces = ["# " + bleach.clean(str(snapshot["title"]), tags=[], strip=True), "", "## Índice", ""]
    for section in snapshot["document"]["sections"]:
        safe_title = bleach.clean(str(section["title"]), tags=[], strip=True)
        pieces.append(f"- [{safe_title}](#{_anchor(section['id'])})")
    for section in snapshot["document"]["sections"]:
        content = section["markdown"]
        def image_replace(match):
            key = _source_id(match.group(2))
            if key in images:
                return f"![{match.group(1)}]({images[key]['data_url']})"
            return "[Imagem omitida: " + match.group(1) + "]"
        content = re.sub(r"!\[([^\]]*)\]\(([^\s)]+)(?:\s+[^)]*)?\)", image_replace, content)
        # Markdown export never embeds executable raw HTML.
        content = sanitize_markdown(content)
        safe_title = bleach.clean(str(section["title"]), tags=[], strip=True)
        pieces += ["", f"<a id=\"{_anchor(section['id'])}\"></a>", "## " + safe_title, "", content]
    if snapshot.get("evidences"):
        pieces += ["", "## Evidências autorizadas", ""]
        for item in snapshot["evidences"]:
            pieces.append(f"- {item['name']} — SHA-256: `{item['sha256']}`; origem: {item['origin']}")
            if item["id"] in images:
                pieces += ["", f"![{item['name']}]({images[item['id']]['data_url']})"]
    return "\n".join(pieces) + "\n"


def render_markdown(content, images=None):
    images = images or {}
    def code_highlight(code, language, _attrs):
        try:
            lexer = get_lexer_by_name(language) if language else TextLexer()
        except Exception:
            lexer = TextLexer()
        return highlight(code, lexer, HtmlFormatter())
    md = MarkdownIt("commonmark", {"html": False, "highlight": code_highlight}).enable("table")
    def image_rule(_renderer, tokens, index, _options, _env):
        token = tokens[index]
        key = _source_id(token.attrGet("src") or "")
        if key not in images:
            return '<span class="image-omitted">[Imagem não incluída]</span>'
        return f'<img src="{images[key]["data_url"]}" alt="{escape(token.content, quote=True)}">'
    md.add_render_rule("image", image_rule)
    rendered = md.render(content)
    return bleach.clean(rendered,
        tags={"p", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "s", "blockquote",
              "ul", "ol", "li", "code", "pre", "a", "img", "hr", "br", "table", "thead", "tbody",
              "tr", "th", "td", "span", "div"},
        attributes={"a": ["href", "title"], "img": ["src", "alt"], "*": ["class"]},
        protocols={"http", "https", "mailto", "data"}, strip=True)


def html_document(snapshot, options, images):
    theme_dark = options.get("theme") == "dark"
    bg, fg = ("#101826", "#e8edf4") if theme_dark else ("#ffffff", "#192333")
    styles = f"body{{background:{bg};color:{fg};max-width:900px;margin:auto;padding:32px;font:16px/1.6 system-ui}}img{{max-width:100%}}pre{{overflow:auto;padding:16px;background:#172333;color:#e8edf4}}table{{border-collapse:collapse}}td,th{{border:1px solid #888;padding:8px}}" + HtmlFormatter().get_style_defs(".highlight")
    body = []
    if options.get("header"):
        body.append("<header>" + escape(options["header"]) + "</header>")
    if options.get("cover", True):
        body.append("<p>" + escape(options.get("brand", "CTF Writeup Studio")) + "</p>")
    body += ["<h1>" + escape(snapshot["title"]) + "</h1>",
             f"<p>Versão {snapshot['version']} · {escape(str(snapshot.get('created_at', '')))}</p>",
             '<nav aria-label="Índice"><h2>Índice</h2><ol>']
    for section in snapshot["document"]["sections"]:
        body.append(f'<li><a href="#{_anchor(section["id"])}">{escape(section["title"])}</a></li>')
    body.append("</ol></nav>")
    for section in snapshot["document"]["sections"]:
        body += [f'<section id="{_anchor(section["id"])}"><h2>{escape(section["title"])}</h2>',
                 render_markdown(section["markdown"], images), "</section>"]
    if snapshot.get("evidences"):
        body.append("<section><h2>Evidências autorizadas</h2>")
        for item in snapshot["evidences"]:
            body += ["<figure>", "<figcaption>" + escape(item["name"]) + " · SHA-256: " + escape(item["sha256"]) + "</figcaption>"]
            if item["id"] in images:
                body.append(f'<img src="{images[item["id"]]["data_url"]}" alt="{escape(item["name"], quote=True)}">')
            body.append("<p>Origem: " + escape(item["origin"]) + "</p></figure>")
        body.append("</section>")
    if options.get("footer"):
        body.append("<footer>" + escape(options["footer"]) + "</footer>")
    return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(snapshot["title"]) + "</title><style>" + styles + "</style></head><body>" + "".join(body) + "</body></html>"


def pdf_document(snapshot, options, images):
    # ReportLab receives BytesIO only. No renderer can fetch network/file URLs.
    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, Table, TableStyle, Image
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles["Normal"].wordWrap = "CJK"
    story = []
    def paragraph(text, style="Normal"):
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), styles[style]))
    if options.get("cover", True):
        paragraph(options.get("brand", "CTF Writeup Studio"))
    paragraph(snapshot["title"], "Title")
    paragraph(f"Versão {snapshot['version']}")
    paragraph("Índice", "Heading2")
    for number, section in enumerate(snapshot["document"]["sections"], 1):
        paragraph(f"{number}. {section['title']}")
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    for section in snapshot["document"]["sections"]:
        paragraph(section["title"], "Heading1")
        tokens = md.parse(section["markdown"])
        table_rows, row_cells, in_table = [], [], False
        for index, token in enumerate(tokens):
            if token.type == "table_open":
                in_table = True; table_rows = []
            elif token.type == "tr_open":
                row_cells = []
            elif token.type == "inline":
                if in_table:
                    row_cells.append(Paragraph(escape(token.content), styles["Normal"]))
                else:
                    previous = tokens[index - 1].type if index else ""
                    paragraph(token.content, "Heading2" if previous == "heading_open" else "Normal")
            elif token.type == "tr_close":
                table_rows.append(row_cells)
            elif token.type == "table_close":
                in_table = False
                if table_rows:
                    table = Table(table_rows, repeatRows=1)
                    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                    story += [table, Spacer(1, 10)]
            elif token.type in {"fence", "code_block"}:
                if token.info:
                    paragraph("Linguagem: " + token.info)
                story.append(Preformatted(token.content, styles["Code"], maxLineLength=95))
        story.append(Spacer(1, 12))
    if snapshot.get("evidences"):
        paragraph("Evidências autorizadas", "Heading1")
    for item in snapshot.get("evidences", []):
        paragraph(item["name"], "Heading2")
        paragraph("SHA-256: " + item["sha256"])
        paragraph("Origem: " + item["origin"])
        if item["id"] in images:
            with PILImage.open(BytesIO(images[item["id"]]["bytes"])) as source:
                source.seek(0)
                rendered = source.convert("RGB")
                normalized = BytesIO(); rendered.save(normalized, "PNG"); normalized.seek(0)
                width, height = rendered.size
            scale = min(480 / width, 600 / height, 1)
            story.append(Image(normalized, width=width * scale, height=height * scale))
    def page(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(40, 810, options.get("header", "")[:160])
        canvas.drawString(40, 25, options.get("footer", "")[:120])
        canvas.drawRightString(555, 25, str(document.page))
        canvas.restoreState()
    SimpleDocTemplate(output, title=snapshot["title"], author=options.get("brand", "CTF Writeup Studio"),
                      topMargin=55, bottomMargin=45).build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()


def export_document(snapshot, options):
    """Returns (bytes, MIME, filename). Original attachments need explicit opt-in."""
    format_name = options["format"]
    images = _image_map(snapshot.get("evidences", []))
    if format_name == "markdown":
        data = markdown_text(snapshot, images).encode("utf-8")
    elif format_name == "html":
        data = html_document(snapshot, options, images).encode("utf-8")
    elif format_name == "json":
        payload = {"schema_version": 1, "title": snapshot["title"], "version": snapshot["version"],
                   "document": snapshot["document"], "evidences": [
                       {key: value for key, value in item.items() if key not in {"storage_key", "original_key"}}
                       for item in snapshot.get("evidences", [])]}
        for item in payload["evidences"]:
            if item["id"] in images:
                item["image_data_url"] = images[item["id"]]["data_url"]
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    else:
        data = pdf_document(snapshot, options, images)
    filename = "writeup-v" + str(snapshot["version"]) + "." + EXTENSION[format_name]
    if options.get("include_originals"):
        zipped = BytesIO()
        with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(filename, data)
            for item in snapshot.get("evidences", []):
                safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", item["name"])[-160:] or "evidence"
                archive.writestr("attachments/" + item["id"] + "-" + safe_name,
                                 read_object(item["original_key"], max_bytes=20971520))
        return zipped.getvalue(), "application/zip", "writeup-v" + str(snapshot["version"]) + ".zip"
    return data, MIME[format_name], filename
