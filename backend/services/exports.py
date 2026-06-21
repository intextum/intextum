"""Helpers for exporting assistant responses as downloadable files."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import quote
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from models.exports import AssistantResponseExportRequest
from services.exports_docx_markdown import (
    _DocxInlineRun,
    _DocxParagraph,
    _inline_runs,
    _markdown_to_docx_paragraphs,
)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

_FILENAME_FORBIDDEN_PATTERN = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_WHITESPACE_PATTERN = re.compile(r"\s+")
_SUPPORTED_DOCX_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpg",
    "image/gif": "gif",
}
_MAX_IMAGE_WIDTH_EMU = 6 * 914400
_MAX_IMAGE_HEIGHT_EMU = 8 * 914400
_PX_TO_EMU = 9525


@dataclass(frozen=True)
class _DocxImageAsset:
    url: str
    filename: str
    extension: str
    media_type: str
    data: bytes
    width_px: int
    height_px: int
    alt_text: str
    relationship_id: str
    part_name: str


@dataclass(frozen=True)
class _DocxHyperlinkTarget:
    url: str
    relationship_id: str


def sanitize_export_filename_base(
    value: str, *, fallback: str = "assistant-response"
) -> str:
    """Return a filesystem-safe filename base while preserving readable Unicode."""
    cleaned = _FILENAME_FORBIDDEN_PATTERN.sub("-", value).strip()
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    cleaned = cleaned.strip(" .-_")
    return cleaned or fallback


def build_content_disposition(filename: str) -> str:
    """Return a UTF-8 aware attachment header for one export filename."""
    safe_filename = sanitize_export_filename_base(filename, fallback="export")
    if "." not in safe_filename:
        safe_filename = f"{safe_filename}.docx"

    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", safe_filename).strip("-_.")
    if not ascii_fallback:
        ascii_fallback = "export.docx"

    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(safe_filename)}"
    )


def _fallback_image_paragraph_xml(paragraph: _DocxParagraph) -> str:
    fallback_text = paragraph.text
    if paragraph.image_url:
        fallback_text = f"{paragraph.text} ({paragraph.image_url})"
    return _paragraph_xml(
        _DocxParagraph(kind="paragraph", text=fallback_text),
        {},
    )


def _image_dimensions_emu(asset: _DocxImageAsset) -> tuple[int, int]:
    width_emu = asset.width_px * _PX_TO_EMU
    height_emu = asset.height_px * _PX_TO_EMU
    scale = min(
        1.0,
        _MAX_IMAGE_WIDTH_EMU / width_emu if width_emu > 0 else 1.0,
        _MAX_IMAGE_HEIGHT_EMU / height_emu if height_emu > 0 else 1.0,
    )
    return max(1, int(width_emu * scale)), max(1, int(height_emu * scale))


def _image_paragraph_xml(paragraph: _DocxParagraph, asset: _DocxImageAsset) -> str:
    width_emu, height_emu = _image_dimensions_emu(asset)
    escaped_name = escape(asset.alt_text or paragraph.text or "Image")
    return (
        "<w:p>"
        "<w:r>"
        "<w:drawing>"
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="1" name="{escaped_name}" descr="{escaped_name}"/>'
        "<wp:cNvGraphicFramePr>"
        '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        "</wp:cNvGraphicFramePr>"
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        "<pic:nvPicPr>"
        f'<pic:cNvPr id="0" name="{escaped_name}" descr="{escaped_name}"/>'
        "<pic:cNvPicPr/>"
        "</pic:nvPicPr>"
        "<pic:blipFill>"
        f'<a:blip r:embed="{asset.relationship_id}"/>'
        "<a:stretch><a:fillRect/></a:stretch>"
        "</pic:blipFill>"
        "<pic:spPr>"
        "<a:xfrm>"
        '<a:off x="0" y="0"/>'
        f'<a:ext cx="{width_emu}" cy="{height_emu}"/>'
        "</a:xfrm>"
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</pic:spPr>"
        "</pic:pic>"
        "</a:graphicData>"
        "</a:graphic>"
        "</wp:inline>"
        "</w:drawing>"
        "</w:r>"
        "</w:p>"
    )


def _paragraph_properties_xml(kind: str) -> str:
    if kind == "heading1":
        return '<w:pPr><w:spacing w:before="240" w:after="160"/></w:pPr>'
    if kind == "heading2":
        return '<w:pPr><w:spacing w:before="180" w:after="120"/></w:pPr>'
    if kind == "heading3":
        return '<w:pPr><w:spacing w:before="120" w:after="80"/></w:pPr>'
    if kind == "bullet":
        return '<w:pPr><w:ind w:left="720" w:hanging="240"/></w:pPr>'
    if kind == "numbered":
        return '<w:pPr><w:ind w:left="720" w:hanging="240"/></w:pPr>'
    if kind == "quote":
        return '<w:pPr><w:ind w:left="720"/><w:spacing w:after="80"/></w:pPr>'
    if kind == "code":
        return '<w:pPr><w:spacing w:after="40"/></w:pPr>'
    if kind in {"table_cell", "table_header"}:
        return '<w:pPr><w:spacing w:after="0"/></w:pPr>'
    return '<w:pPr><w:spacing w:after="120"/></w:pPr>'


def _run_properties_xml(kind: str, *, hyperlink: bool = False) -> str:
    properties: list[str] = []
    if kind == "heading1":
        properties.extend(["<w:b/>", '<w:sz w:val="34"/>'])
    elif kind == "heading2":
        properties.extend(["<w:b/>", '<w:sz w:val="28"/>'])
    elif kind == "heading3":
        properties.extend(["<w:b/>", '<w:sz w:val="24"/>'])
    elif kind == "quote":
        properties.append("<w:i/>")
    elif kind == "code":
        properties.extend(
            [
                '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/>',
                '<w:sz w:val="20"/>',
            ]
        )
    elif kind == "table_header":
        properties.append("<w:b/>")

    if hyperlink:
        properties.extend(['<w:color w:val="0563C1"/>', '<w:u w:val="single"/>'])

    return f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""


def _run_xml(
    kind: str,
    run: _DocxInlineRun,
    hyperlink_targets_by_url: dict[str, _DocxHyperlinkTarget],
) -> str:
    escaped_text = escape(run.text)
    run_xml = (
        "<w:r>"
        f"{_run_properties_xml(kind, hyperlink=run.hyperlink_url is not None)}"
        f'<w:t xml:space="preserve">{escaped_text}</w:t>'
        "</w:r>"
    )
    if run.hyperlink_url:
        target = hyperlink_targets_by_url.get(run.hyperlink_url)
        if target is not None:
            return (
                f'<w:hyperlink r:id="{target.relationship_id}">{run_xml}</w:hyperlink>'
            )
    return run_xml


def _paragraph_xml(
    paragraph: _DocxParagraph,
    hyperlink_targets_by_url: dict[str, _DocxHyperlinkTarget],
) -> str:
    runs = _inline_runs(paragraph.text)
    if not runs:
        runs = [_DocxInlineRun(text=paragraph.text or "")]
    run_xml = "".join(
        _run_xml(paragraph.kind, run, hyperlink_targets_by_url) for run in runs
    )
    return f"<w:p>{_paragraph_properties_xml(paragraph.kind)}{run_xml}</w:p>"


def _table_cell_xml(
    text: str,
    *,
    is_header: bool,
    hyperlink_targets_by_url: dict[str, _DocxHyperlinkTarget],
) -> str:
    paragraph = _DocxParagraph(
        kind="table_header" if is_header else "table_cell",
        text=text,
    )
    return (
        "<w:tc>"
        '<w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>'
        f"{_paragraph_xml(paragraph, hyperlink_targets_by_url)}"
        "</w:tc>"
    )


def _table_xml(
    paragraph: _DocxParagraph,
    hyperlink_targets_by_url: dict[str, _DocxHyperlinkTarget],
) -> str:
    rows = list(paragraph.table_rows)
    if not rows:
        return ""

    row_xml: list[str] = []
    for row_index, row in enumerate(rows):
        cells_xml = "".join(
            _table_cell_xml(
                cell,
                is_header=row_index == 0,
                hyperlink_targets_by_url=hyperlink_targets_by_url,
            )
            for cell in row
        )
        row_xml.append(f"<w:tr>{cells_xml}</w:tr>")

    return (
        "<w:tbl>"
        "<w:tblPr>"
        '<w:tblW w:w="0" w:type="auto"/>'
        "<w:tblBorders>"
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        "</w:tblBorders>"
        "</w:tblPr>"
        f"{''.join(row_xml)}"
        "</w:tbl>"
    )


def _document_xml(
    paragraphs: list[_DocxParagraph],
    image_assets_by_url: dict[str, _DocxImageAsset],
    hyperlink_targets_by_url: dict[str, _DocxHyperlinkTarget],
) -> str:
    body_parts: list[str] = []
    for paragraph in paragraphs:
        if paragraph.kind == "table":
            body_parts.append(_table_xml(paragraph, hyperlink_targets_by_url))
            continue
        if paragraph.kind == "image":
            asset = (
                image_assets_by_url.get(paragraph.image_url or "")
                if paragraph.image_url
                else None
            )
            body_parts.append(
                _image_paragraph_xml(paragraph, asset)
                if asset is not None
                else _fallback_image_paragraph_xml(paragraph)
            )
            continue
        body_parts.append(_paragraph_xml(paragraph, hyperlink_targets_by_url))

    body = "".join(body_parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<w:document "
        'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14">'
        f"<w:body>{body}"
        "<w:sectPr>"
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
        "</w:body></w:document>"
    )


def _core_properties_xml(title: str) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    escaped_title = escape(title)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties "
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escaped_title}</dc:title>"
        "<dc:creator>intextum</dc:creator>"
        "<cp:lastModifiedBy>intextum</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _build_hyperlink_targets(
    paragraphs: list[_DocxParagraph],
) -> list[_DocxHyperlinkTarget]:
    targets: list[_DocxHyperlinkTarget] = []
    seen_urls: set[str] = set()
    for paragraph in paragraphs:
        texts = (
            [cell for row in paragraph.table_rows for cell in row]
            if paragraph.kind == "table"
            else [paragraph.text]
        )
        for text in texts:
            for run in _inline_runs(text):
                url = run.hyperlink_url
                if not url or url in seen_urls:
                    continue
                targets.append(
                    _DocxHyperlinkTarget(
                        url=url,
                        relationship_id=f"rIdLink{len(targets) + 1}",
                    )
                )
                seen_urls.add(url)
    return targets


def _document_relationships_xml(
    image_assets: list[_DocxImageAsset],
    hyperlink_targets: list[_DocxHyperlinkTarget],
) -> str:
    relationships = []
    for asset in image_assets:
        relationships.append(
            "<Relationship "
            f'Id="{asset.relationship_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="media/{asset.part_name.split("/")[-1]}"/>'
        )
    for target in hyperlink_targets:
        relationships.append(
            "<Relationship "
            f'Id="{target.relationship_id}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            f'Target="{escape(target.url)}" TargetMode="External"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships)
        + "</Relationships>"
    )


def _build_embedded_image_assets(
    payload: AssistantResponseExportRequest,
) -> list[_DocxImageAsset]:
    assets: list[_DocxImageAsset] = []
    seen_urls: set[str] = set()
    for index, image in enumerate(payload.embedded_images, start=1):
        if image.url in seen_urls:
            continue
        extension = _SUPPORTED_DOCX_IMAGE_TYPES.get(image.media_type.lower())
        if extension is None:
            continue
        try:
            data = base64.b64decode(image.data_base64, validate=True)
        except (ValueError, TypeError):
            continue
        if not data:
            continue

        sanitized_name = sanitize_export_filename_base(
            image.filename, fallback=f"image-{index}"
        )
        assets.append(
            _DocxImageAsset(
                url=image.url,
                filename=sanitized_name,
                extension=extension,
                media_type=image.media_type.lower(),
                data=data,
                width_px=image.width_px,
                height_px=image.height_px,
                alt_text=image.alt_text or sanitized_name,
                relationship_id=f"rIdImage{len(assets) + 1}",
                part_name=f"word/media/image{len(assets) + 1}.{extension}",
            )
        )
        seen_urls.add(image.url)
    return assets


def _content_types_xml(image_assets: list[_DocxImageAsset]) -> str:
    image_defaults = "".join(
        f'<Default Extension="{extension}" ContentType="{media_type}"/>'
        for media_type, extension in sorted(
            {(asset.media_type, asset.extension) for asset in image_assets},
            key=lambda item: item[1],
        )
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{image_defaults}"
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def build_docx_export(payload: AssistantResponseExportRequest) -> bytes:
    """Render one normalized assistant-response export payload to DOCX bytes."""
    image_assets = _build_embedded_image_assets(payload)
    image_assets_by_url = {asset.url: asset for asset in image_assets}
    paragraphs = _markdown_to_docx_paragraphs(payload.markdown, title=payload.title)
    hyperlink_targets = _build_hyperlink_targets(paragraphs)
    hyperlink_targets_by_url = {target.url: target for target in hyperlink_targets}
    output = BytesIO()

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(image_assets))
        archive.writestr(
            "_rels/.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                '<Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
                'Target="docProps/core.xml"/>'
                '<Relationship Id="rId3" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
                'Target="docProps/app.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "docProps/app.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
                'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
                "<Application>intextum</Application>"
                "</Properties>"
            ),
        )
        archive.writestr("docProps/core.xml", _core_properties_xml(payload.title))
        archive.writestr(
            "word/document.xml",
            _document_xml(
                paragraphs,
                image_assets_by_url,
                hyperlink_targets_by_url,
            ),
        )
        if image_assets or hyperlink_targets:
            archive.writestr(
                "word/_rels/document.xml.rels",
                _document_relationships_xml(image_assets, hyperlink_targets),
            )
            for asset in image_assets:
                archive.writestr(asset.part_name, asset.data)

    return output.getvalue()
