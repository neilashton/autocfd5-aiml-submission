#!/usr/bin/env python3
"""Build the public AutoCFD5 AIML participant submission guide."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#176B87")
CYAN = colors.HexColor("#22B8CF")
ORANGE = colors.HexColor("#F59F00")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
PALE = colors.HexColor("#F0F7FA")
PALE_BLUE = colors.HexColor("#E7F5F8")
PALE_ORANGE = colors.HexColor("#FFF4D6")
LINE = colors.HexColor("#D9E2EC")
WHITE = colors.white

PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = 22 * mm
RIGHT = 20 * mm
TOP = 22 * mm
BOTTOM = 19 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT

REPOSITORY_URL = "https://github.com/neilashton/autocfd5-aiml-submission"
SUPPORT_URL = f"{REPOSITORY_URL}/releases/tag/support-v1"
DATASET_URL = "https://huggingface.co/datasets/neashton/drivaerml"
DROPBOX_REQUEST_URL = "https://www.dropbox.com/request/A6cJNTT9egFtYiFICjAi"
DATASET_REVISION = "7a5c0948ce27be709b1116a3a190f806e7a8f79f"
SUPPORT_ARCHIVE_SHA256 = "5ebcf744be53016bd158236d1f4af3290ff399b323c0e11a49c37ea9a6c686f6"
SUPPORT_INDEX_SHA256 = "f47f8c3ed7a56632b0c02a3aec793e4cd823d5d04d5264d00fcd419bf11c0f4f"
REGIONAL_CONTRACT_SHA256 = "2bfd372817989112642056e4c76cfb418dbdcee445c57ee20ca37ee9ca158583"
EVALUATOR_TAG = "evaluator-v1.1.5"
GUIDE_VERSION = "1.1.5"
GUIDE_DATE = "2 September 2026"


def make_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=CYAN,
            spaceAfter=8,
            tracking=1.5,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=31,
            leading=35,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=13,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=15,
            leading=21,
            textColor=colors.HexColor("#D9EEF3"),
            spaceAfter=18,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=14,
            textColor=colors.HexColor("#D9E2EC"),
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=25,
            textColor=NAVY,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13.5,
            leading=16,
            textColor=BLUE,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.3,
            leading=13,
            textColor=INK,
            spaceBefore=5,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.35,
            leading=13.2,
            textColor=INK,
            spaceAfter=5.5,
        ),
        "small": ParagraphStyle(
            "small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10.6,
            textColor=MUTED,
            spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.15,
            leading=12.7,
            leftIndent=12,
            firstLineIndent=-8,
            bulletIndent=2,
            textColor=INK,
            spaceAfter=3.5,
        ),
        "number": ParagraphStyle(
            "number",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.3,
            leading=12.7,
            leftIndent=18,
            firstLineIndent=-16,
            textColor=INK,
            spaceAfter=5,
        ),
        "code": ParagraphStyle(
            "code",
            parent=sample["Code"],
            fontName="Courier",
            fontSize=6.9,
            leading=9.2,
            textColor=colors.HexColor("#102A43"),
            leftIndent=0,
            rightIndent=0,
            spaceAfter=0,
        ),
        "table_head": ParagraphStyle(
            "table_head",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.3,
            textColor=WHITE,
            alignment=TA_LEFT,
        ),
        "table": ParagraphStyle(
            "table",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.45,
            leading=9.8,
            textColor=INK,
        ),
        "table_bold": ParagraphStyle(
            "table_bold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.45,
            leading=9.8,
            textColor=INK,
        ),
        "callout_title": ParagraphStyle(
            "callout_title",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11.3,
            textColor=NAVY,
            spaceAfter=3,
        ),
        "callout_body": ParagraphStyle(
            "callout_body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=12,
            textColor=INK,
        ),
        "hash": ParagraphStyle(
            "hash",
            parent=sample["BodyText"],
            fontName="Courier",
            fontSize=6.6,
            leading=8.7,
            textColor=INK,
            wordWrap="CJK",
        ),
        "toc": ParagraphStyle(
            "toc",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10.3,
            leading=14,
            textColor=NAVY,
            leftIndent=22,
            firstLineIndent=-22,
            spaceAfter=5,
        ),
    }


STYLES = make_styles()


class AccentRule(Flowable):
    def __init__(self, width: float = CONTENT_WIDTH, color: colors.Color = CYAN):
        super().__init__()
        self.width = width
        self.height = 3
        self.color = color

    def draw(self) -> None:
        self.canv.setFillColor(self.color)
        self.canv.roundRect(0, 0, self.width, 3, 1.5, fill=1, stroke=0)


def para(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", STYLES["bullet"])


def numbered(number: int, text: str) -> Paragraph:
    return Paragraph(f"<font color='#176B87'>{number:02d}</font>  {text}", STYLES["number"])


def code_block(text: str) -> Table:
    block = Preformatted(text.strip("\n"), STYLES["code"])
    table = Table([[block]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDF2F7")),
                ("BOX", (0, 0), (-1, -1), 0.45, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def callout(title: str, body: str, *, tone: str = "blue") -> KeepTogether:
    background = PALE_ORANGE if tone == "orange" else PALE_BLUE
    bar = ORANGE if tone == "orange" else CYAN
    content = [para(title, "callout_title"), para(body, "callout_body")]
    table = Table([["", content]], colWidths=[4, CONTENT_WIDTH - 4], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BACKGROUND", (0, 0), (0, 0), bar),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 10),
                ("TOPPADDING", (1, 0), (1, 0), 8),
                ("BOTTOMPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    return KeepTogether([table, Spacer(1, 7)])


def data_table(
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    *,
    compact: bool = False,
) -> Table:
    head = [para(value, "table_head") for value in headers]
    body = [[para(value, "table") for value in row] for row in rows]
    table = Table([head, *body], colWidths=widths, repeatRows=1, hAlign="LEFT")
    padding = 3.5 if compact else 5
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]
    for row_index in range(1, len(rows) + 1):
        if row_index % 2 == 0:
            commands.append(("BACKGROUND", (0, row_index), (-1, row_index), PALE))
    table.setStyle(TableStyle(commands))
    return table


def hash_table(rows: list[tuple[str, str]]) -> Table:
    data = [[para(label, "table_bold"), para(value, "hash")] for label, value in rows]
    table = Table(data, colWidths=[39 * mm, CONTENT_WIDTH - 39 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def draw_cover(canvas, doc) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setTitle("AutoCFD5 AIML DrivAerML Participant Submission Instructions")
    canvas.setAuthor("AutoCFD5 organisers")
    canvas.setSubject("Participant evaluation, packaging and confidential delivery procedure")
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#153D59"))
    canvas.circle(PAGE_WIDTH + 10 * mm, PAGE_HEIGHT - 16 * mm, 68 * mm, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.circle(PAGE_WIDTH - 8 * mm, PAGE_HEIGHT - 10 * mm, 42 * mm, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, 0, 7 * mm, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(ORANGE)
    canvas.rect(7 * mm, 0, 1.4 * mm, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#2D5C75"))
    canvas.setLineWidth(0.8)
    for offset in range(0, 9):
        y = 31 * mm + offset * 7 * mm
        canvas.line(22 * mm, y, PAGE_WIDTH - 22 * mm, y)
    canvas.restoreState()


def draw_content(canvas, doc) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(LEFT, PAGE_HEIGHT - 12 * mm, "AutoCFD5 AIML  /  DrivAerML")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.2)
    right_label = "PARTICIPANT SUBMISSION GUIDE"
    canvas.drawRightString(PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 12 * mm, right_label)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(1.1)
    canvas.line(LEFT, PAGE_HEIGHT - 15 * mm, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 15 * mm)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.45)
    canvas.line(LEFT, 13 * mm, PAGE_WIDTH - RIGHT, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(LEFT, 8.5 * mm, f"Version {GUIDE_VERSION}  |  {GUIDE_DATE}")
    page_label = f"{canvas.getPageNumber():02d}"
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(NAVY)
    canvas.drawRightString(PAGE_WIDTH - RIGHT, 8.5 * mm, page_label)
    canvas.restoreState()


class GuideDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=LEFT,
            rightMargin=RIGHT,
            topMargin=TOP,
            bottomMargin=BOTTOM,
            title="AutoCFD5 AIML DrivAerML Participant Submission Instructions",
            author="AutoCFD5 organisers",
        )
        cover_frame = Frame(
            LEFT,
            BOTTOM,
            CONTENT_WIDTH,
            PAGE_HEIGHT - TOP - BOTTOM,
            id="cover-frame",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        content_frame = Frame(
            LEFT,
            BOTTOM,
            CONTENT_WIDTH,
            PAGE_HEIGHT - TOP - BOTTOM,
            id="content-frame",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="cover",
                    frames=[cover_frame],
                    onPage=draw_cover,
                    autoNextPageTemplate="content",
                ),
                PageTemplate(id="content", frames=[content_frame], onPage=draw_content),
            ]
        )


def section_title(kicker: str, title: str, introduction: str | None = None) -> list[Flowable]:
    items: list[Flowable] = [
        para(kicker.upper(), "small"),
        para(title, "h1"),
        AccentRule(35 * mm),
        Spacer(1, 7),
    ]
    if introduction:
        items.append(para(introduction))
    return items


def cover_story() -> list[Flowable]:
    return [
        Spacer(1, 37 * mm),
        para("AUTO CFD WORKSHOP SERIES", "cover_kicker"),
        para("AutoCFD5 AIML<br/>DrivAerML", "cover_title"),
        para("Participant Submission Instructions", "cover_subtitle"),
        AccentRule(58 * mm, ORANGE),
        Spacer(1, 12 * mm),
        para(
            "A reproducible route to export complete native-cell surface predictions, optionally "
            "include complete volume predictions, run the approved evaluator, inspect results, "
            "and deliver a verified entry.",
            "cover_subtitle",
        ),
        Spacer(1, 17 * mm),
        Table(
            [
                [para("PUBLIC TOOLING", "cover_kicker"), para("CONFIDENTIAL ENTRIES", "cover_kicker")],
                [
                    para(
                        "Evaluator code, documentation, immutable profile support, and the report-only regional contract.",
                        "cover_meta",
                    ),
                    para("Participant result packages use a private upload-only route.", "cover_meta"),
                ],
            ],
            colWidths=[CONTENT_WIDTH / 2 - 4 * mm, CONTENT_WIDTH / 2 - 4 * mm],
            hAlign="LEFT",
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBEFORE", (1, 0), (1, -1), 0.7, colors.HexColor("#4F7186")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 8 * mm),
                    ("LEFTPADDING", (1, 0), (1, -1), 8 * mm),
                    ("RIGHTPADDING", (1, 0), (1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            ),
        ),
        Spacer(1, 20 * mm),
        para(f"Version {GUIDE_VERSION}  /  {GUIDE_DATE}", "cover_meta"),
        para(
            f'<link href="{REPOSITORY_URL}" color="#22B8CF">{REPOSITORY_URL}</link>',
            "cover_meta",
        ),
        NextPageTemplate("content"),
        PageBreak(),
    ]


def start_here() -> list[Flowable]:
    items = section_title(
        "01 / Start here",
        "The complete route, at a glance",
        f'You run the official evaluator on your own machine using the <link href="{DATASET_URL}">'
        "pinned DrivAerML dataset</link>. The public repository carries the code and fixed support "
        "data; your predictions and results remain under your control until you use the private "
        "workshop upload route. The next section lists every official split.",
    )
    items.extend(
        [
            callout(
                "Mandatory in both scopes: the complete native surface",
                "For <b>every selected test case</b>, export <font name='Courier'>pMeanTrim</font> and "
                "<font name='Courier'>wallShearStressMeanTrim</font> for <b>every cell</b> of the pinned "
                "surface VTP. Inference may run in chunks or on another representation, but the final "
                "surface export must map back to every native <font name='Courier'>raw_cell_id</font> "
                "exactly once, with no missing or duplicate cells. A sampled or partial surface is not accepted.",
                tone="orange",
            ),
            data_table(
                ["prediction_scope", "Required predictions", "Maximum overall score"],
                [
                    [
                        "surface_and_volume",
                        "Complete native surface plus complete native-volume pMeanTrim and UMeanTrim. This is the legacy default.",
                        "100 / 100",
                    ],
                    [
                        "surface_only",
                        "Complete native surface; omit volume predictions. Volume fields and velocity profiles receive zero component points.",
                        "60 / 100",
                    ],
                ],
                [40 * mm, CONTENT_WIDTH - 75 * mm, 35 * mm],
                compact=True,
            ),
            para(
                "Surface-only entries do not use dummy volume fields. Their unavailable scientific "
                "metric values are absent, the three unavailable component scores are exactly zero, "
                "and the approved weights are not renormalized.",
                "small",
            ),
            Spacer(1, 2),
            numbered(1, f"Clone the evaluator and select the frozen <b>{EVALUATOR_TAG}</b> release."),
            numbered(2, "Fetch the immutable profile-support bundle and the pinned native test files."),
            numbered(3, "Choose one prediction scope in <b>entry.json</b> and export every required native cell for every selected case."),
            numbered(4, "Validate the entry, then evaluate one case while developing your export."),
            numbered(5, "Evaluate the official <b>full</b> split as the minimum common comparison."),
            numbered(6, "Inspect <b>result.json</b> and selected local HTML profile reports."),
            numbered(7, "Create and verify one deterministic ZIP, then upload it confidentially."),
            callout(
                "Public repository does not mean public submissions",
                "Do not commit predictions or results, attach them to an issue, or open a pull request. "
                f'The organisers provide an <link href="{DROPBOX_REQUEST_URL}">AutoCFD Dropbox File '
                "Request</link> for confidential upload. The email is only a checksum receipt.",
                tone="orange",
            ),
            para("Who is responsible for what", "h2"),
            data_table(
                ["Party", "Responsibility"],
                [
                    [
                        "Participant",
                        "Export native-order predictions; run, inspect, package, verify, upload, and retain the original ZIP and checksum.",
                    ],
                    [
                        "Evaluator",
                        "Verify fixed inputs; calculate fields, forces, and profiles; aggregate the full split; write compact, deterministic outputs.",
                    ],
                    [
                        "Organisers",
                        "Provide the private upload link; verify package identity and split completeness; preserve the received ZIP under the workshop embargo.",
                    ],
                ],
                [31 * mm, CONTENT_WIDTH - 31 * mm],
            ),
            para("What you hand in", "h2"),
            bullet("One verified <b>.zip</b> produced by <font name='Courier'>autocfd5-aiml package</font>."),
            bullet("A short email containing the committee-issued submission ID, filename, and exact SHA-256."),
            bullet("No raw native prediction files unless the organisers explicitly request a separately hosted immutable artifact."),
            PageBreak(),
        ]
    )
    return items


def split_choices() -> list[Flowable]:
    items = section_title(
        "02 / Official splits",
        "Use Full as the common baseline",
        "The AutoCFD organising committee asks every participant to evaluate the official Full split "
        "as the minimum common comparison. You are welcome to test the other official splits too.",
    )
    items.extend(
        [
            callout(
                "Committee recommendation",
                "Use <b>split_id = full</b> for the primary submission. Official split membership is "
                "frozen in the evaluator, so participants do not need to repeat its training and "
                "validation IDs in <font name='Courier'>entry.json</font>.",
                tone="orange",
            ),
            data_table(
                ["Official split", "Train", "Validation", "Test", "Case set"],
                [
                    ["full", "400", "34", "50", "Standard - requested baseline"],
                    ["medium", "133", "34", "50", "Standard"],
                    ["scarce", "67", "34", "50", "Standard"],
                    ["super_scarce", "11", "34", "50", "Standard"],
                    ["geometry", "339", "48", "97", "Geometry"],
                    ["high_drag", "339", "48", "97", "High drag"],
                    ["low_drag", "339", "48", "97", "Low drag"],
                    ["rear_separation", "339", "48", "97", "Rear separation"],
                ],
                [39 * mm, 18 * mm, 24 * mm, 18 * mm, CONTENT_WIDTH - 99 * mm],
                compact=True,
            ),
            para("If you use a custom split", "h2"),
            para(
                "The organisers strongly recommend the official splits. If an additional split is not "
                "one of those above, give it a new safe <font name='Courier'>split_id</font> and include "
                "all three ordered run-ID arrays in <font name='Courier'>entry.json</font>:",
            ),
            code_block(
                """
{
  "split_id": "my-custom-study",
  "train_case_ids": ["run_1", "run_2"],
  "validation_case_ids": ["run_3"],
  "test_case_ids": ["run_4", "run_5"]
}
"""
            ),
            bullet("Each array must be non-empty, unique, use <font name='Courier'>run_N</font> IDs from the pinned dataset, and be disjoint from the other two arrays."),
            bullet("The evaluator writes <font name='Courier'>custom-split.json</font> into the verified result package for the organisers."),
            code_block(
                """
autocfd5-aiml fetch-data --entry-root my-entry \\
  --destination /data/drivaerml --dry-run
"""
            ),
            PageBreak(),
        ]
    )
    return items


def setup_and_inputs() -> list[Flowable]:
    items = section_title(
        "03 / Environment",
        "Install once; pin everything",
        "Run the scientific calculation on Linux with Python 3.12. The evaluator pins NumPy and VTK "
        "because native-file handling and numerical reproducibility are part of the contract.",
    )
    items.extend(
        [
            callout(
                "Required environment",
                "Linux; Python >=3.12,<3.13; NumPy 2.2.6; VTK 9.5.2; Git; GitHub CLI "
                "(<font name='Courier'>gh</font>); and Hugging Face CLI (<font name='Courier'>hf</font>). "
                "A Dockerfile using Python 3.12.13 is included when a clean container is preferable.",
            ),
            para("Clone and install", "h2"),
            code_block(
                """
git clone https://github.com/neilashton/autocfd5-aiml-submission.git
cd autocfd5-aiml-submission
git checkout evaluator-v1.1.5

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
autocfd5-aiml --help
"""
            ),
            Spacer(1, 6),
            para("Fetch and verify profile support", "h2"),
            code_block(
                """
autocfd5-aiml fetch-support --destination support/native-v1
"""
            ),
            para(
                "The command downloads the <b>support-v1</b> release asset, verifies its archive hash, "
                "extracts it safely, and verifies <b>index.json</b>. It refuses a non-empty destination.",
                "small",
            ),
            para("Inspect the native-data download before starting it", "h2"),
            code_block(
                """
autocfd5-aiml fetch-data \\
  --split-id full \\
  --prediction-scope surface_and_volume \\
  --destination /data/drivaerml \\
  --dry-run

# Remove --dry-run only when the location and required storage are ready.
autocfd5-aiml fetch-data \\
  --split-id full \\
  --prediction-scope surface_and_volume \\
  --destination /data/drivaerml
"""
            ),
            para(
                "The native files are very large. The dry run lists the exact pinned files and sizes. "
                "Replace <font name='Courier'>surface_and_volume</font> with "
                "<font name='Courier'>surface_only</font> to omit native volume parts, or use "
                "<font name='Courier'>--entry-root my-entry</font> after creating the entry so the "
                "command reads its exact cases and scope. The final dataset root must contain "
                "<font name='Courier'>force_mom_constref_all.csv</font> "
                "and each selected <font name='Courier'>run_N/</font> directory in the downloaded layout.",
                "small",
            ),
            para("Immutable identities", "h2"),
            hash_table(
                [
                    ("Dataset", f'<link href="{DATASET_URL}">neashton/drivaerml</link>'),
                    ("Dataset revision", DATASET_REVISION),
                    ("Support release", f'<link href="{SUPPORT_URL}">support-v1</link>'),
                    ("Support ZIP SHA-256", SUPPORT_ARCHIVE_SHA256),
                    ("Support index SHA-256", SUPPORT_INDEX_SHA256),
                    ("Regional report contract SHA-256", REGIONAL_CONTRACT_SHA256),
                ]
            ),
            PageBreak(),
        ]
    )
    return items


def entry_metadata() -> list[Flowable]:
    items = section_title(
        "04 / Entry metadata",
        "Declare the entry and exact split",
        "Use the exact submission ID sent to you by the AutoCFD organising committee. Start from the "
        "supplied Full-split example and keep its test-case membership and order unchanged.",
    )
    items.extend(
        [
            para("Create a working entry", "h2"),
            code_block(
                """
cp -R examples/entry my-entry
"""
            ),
            Spacer(1, 5),
            data_table(
                ["entry.json key", "Rule"],
                [
                    ["schema", "Keep <font name='Courier'>autocfd5-aiml-entry-v1</font>."],
                    ["schema_version", "Keep integer <font name='Courier'>1</font>."],
                    ["submission_id", "Enter the exact ID sent by the AutoCFD organising committee. It uses lowercase letters, digits, dot, dash, or underscore; at most 80 characters."],
                    ["method_name", "Human-readable method name, 1-200 characters."],
                    ["contact_email", "Email monitored by the participant."],
                    ["split_id", "Keep <font name='Courier'>full</font> for the requested baseline."],
                    ["prediction_scope", "Choose <font name='Courier'>surface_and_volume</font> or <font name='Courier'>surface_only</font>. State it explicitly; omission retains legacy full-field behaviour."],
                    ["force_prediction_source", "Use <font name='Courier'>field_integrated</font> (default), or <font name='Courier'>direct_coefficients</font> with one complete direct-force file per test case."],
                    ["test_case_ids", "Copy the example exactly. Membership and order are both checked."],
                    ["prediction_artifact", "Optional; only for an organiser-requested private immutable raw artifact."],
                ],
                [39 * mm, CONTENT_WIDTH - 39 * mm],
                compact=True,
            ),
            para("Minimal shape", "h2"),
            code_block(
                """
{
  "schema": "autocfd5-aiml-entry-v1",
  "schema_version": 1,
  "submission_id": "assigned-submission-id",
  "method_name": "Method display name",
  "contact_email": "participant@example.org",
  "split_id": "full",
  "prediction_scope": "surface_and_volume",
  "force_prediction_source": "field_integrated",
  "test_case_ids": [ ...copy the complete example array exactly... ]
}
"""
            ),
            para(
                "The ellipsis above is explanatory and is not valid JSON. Copy "
                "<font name='Courier'>examples/entry/entry.json</font>, which contains all 50 IDs.",
                "small",
            ),
            para("Validate before producing every case", "h2"),
            code_block("autocfd5-aiml validate-entry my-entry"),
            callout(
                "Validation has two layers",
                "<font name='Courier'>validate-entry</font> checks metadata and split declarations. "
                "For an official split it requires the frozen test membership and order; for a custom "
                "split it requires complete, disjoint, known train, validation, and test IDs. The full "
                "evaluation requires a valid complete surface manifest for every test case and, only "
                "for <font name='Courier'>surface_and_volume</font>, a valid complete volume manifest.",
            ),
            PageBreak(),
        ]
    )
    return items


def prediction_format() -> list[Flowable]:
    items = section_title(
        "05 / Predictions",
        "Export native cells, without reordering",
        "Every case contains a complete surface manifest plus one or more compressed NPZ chunks. "
        "Full-field entries also contain a complete volume manifest. Raw cell IDs restore native "
        "order and must cover every supplied native-cell range exactly.",
    )
    items.extend(
        [
            code_block(
                """
my-entry/
  entry.json
  cases/
    run_11/
      surface/
        manifest.json
        chunks/chunk-00000.npz
      volume/                 # surface_and_volume only
        manifest.json
        chunks/chunk-00000.npz
      direct-force-coefficients.json  # direct_coefficients only
    ...one directory for every case in the selected split...
"""
            ),
            callout(
                "Surface-only directory rule",
                "With <font name='Courier'>prediction_scope = surface_only</font>, stop after the "
                "surface chunks and omit <font name='Courier'>volume/</font>. Do not create zero or "
                "dummy volume arrays. The evaluator records volume pressure, volume velocity, and "
                "velocity profiles as unavailable and gives those components zero points.",
                tone="orange",
            ),
            callout(
                "Optional direct force route",
                "The default <font name='Courier'>field_integrated</font> route derives coefficients from submitted surface fields. "
                "To score direct force output, set <font name='Courier'>force_prediction_source = direct_coefficients</font> and "
                "place <font name='Courier'>direct-force-coefficients.json</font> in every test-case directory. It supplies only "
                "<font name='Courier'>Cd</font>, <font name='Courier'>Clf</font>, and <font name='Courier'>Clr</font> in the fixed "
                "constant-reference convention; the evaluator derives lift and pitch. Surface fields remain mandatory.",
            ),
            para("Required NPZ arrays", "h2"),
            data_table(
                ["Association", "Array", "Dtype", "Shape / meaning"],
                [
                    ["Surface", "raw_cell_id", "int64", "<font name='Courier'>(rows,)</font>; native polygon ID"],
                    ["Surface", "pMeanTrim", "float32/64", "<font name='Courier'>(rows,)</font>; mean pressure"],
                    ["Surface", "wallShearStressMeanTrim", "float32/64", "<font name='Courier'>(rows, 3)</font>; wall-shear vector"],
                    ["Volume (full only)", "raw_cell_id", "int64", "<font name='Courier'>(rows,)</font>; native volume-cell ID"],
                    ["Volume (full only)", "pMeanTrim", "float32/64", "<font name='Courier'>(rows,)</font>; mean pressure"],
                    ["Volume (full only)", "UMeanTrim", "float32/64", "<font name='Courier'>(rows, 3)</font>; mean velocity vector"],
                ],
                [24 * mm, 46 * mm, 25 * mm, CONTENT_WIDTH - 95 * mm],
                compact=True,
            ),
            para("Closed-manifest requirements", "h2"),
            bullet("Surface association is <font name='Courier'>CellData</font> with support ID <font name='Courier'>surface_native_cells</font>."),
            bullet("The manifest declares case ID, total row count, field component counts, and every chunk."),
            bullet("Each chunk declares file, SHA-256, row count, and half-open raw-ID range."),
            bullet("Values must be finite; unknown or missing keys fail validation."),
            bullet("IDs must cover <font name='Courier'>[0, total_row_count)</font> once, with no gaps or duplicates."),
            bullet("The complete surface is mandatory in both scopes; a sampled or partial surface fails validation."),
            bullet("Use at most 1,000,000 rows per chunk unless the organisers publish another limit."),
            PageBreak(),
        ]
    )
    return items


def development_test() -> list[Flowable]:
    items = section_title(
        "06 / Development check",
        "Prove one case before the full run",
        "Use a selected split case such as run_11 to catch layout, dtype, hash, ID-coverage, and "
        "native-data problems before committing resources to all 50 cases.",
    )
    items.extend(
        [
            para("Evaluate one case", "h2"),
            code_block(
                """
mkdir -p output/dev

autocfd5-aiml evaluate-case \\
  --case-id run_11 \\
  --dataset-root /data/drivaerml \\
  --support-root support/native-v1 \\
  --surface-manifest my-entry/cases/run_11/surface/manifest.json \\
  --volume-manifest my-entry/cases/run_11/volume/manifest.json \\
  --output output/dev/run_11.json
"""
            ),
            para("For a surface-only development check", "h2"),
            code_block(
                """
autocfd5-aiml evaluate-case \\
  --case-id run_11 \\
  --prediction-scope surface_only \\
  --dataset-root /data/drivaerml \\
  --support-root support/native-v1 \\
  --surface-manifest my-entry/cases/run_11/surface/manifest.json \\
  --output output/dev/run_11-surface-only.json
"""
            ),
            callout(
                "A one-case result is diagnostic, not an official result",
                "It contains every metric available in the declared scope, integrated force coefficients, "
                "and available profile loss statistics for that case. Force and profile R2 require variation across "
                "the complete test split, so a single case cannot produce official component or overall scores.",
                tone="orange",
            ),
            para("Check the result deliberately", "h2"),
            data_table(
                ["Check", "Expected outcome"],
                [
                    ["Native identities", "Every required boundary, area, and full-field volume part matches its pinned size and SHA-256."],
                    ["Prediction coverage", "Surface IDs are complete and unique; full-field entries also have complete unique volume IDs."],
                    ["Numerics", "All prediction values and all written JSON numbers are finite."],
                    ["Forces", "Native surface coefficients are always integrated. Direct-route entries also supply Cd, Clf, and Clr under the fixed convention."],
                    ["Profiles", "Forty identities are retained. Surface-only entries mark all 32 velocity rows unavailable without prediction values; Cp remains available."],
                    ["Regional reports", "Surface regions are always present; volume regions appear only for full-field entries. All have zero scoring weight."],
                    ["Gaps", "Unsupported intervals remain separate segments; no line is drawn or integrated across them."],
                ],
                [38 * mm, CONTENT_WIDTH - 38 * mm],
            ),
            para("When the output already exists", "h2"),
            para(
                "The evaluator refuses to overwrite a case result. This is intentional. Use a new output "
                "filename after changing predictions, so every test result remains attributable to one input set.",
            ),
            PageBreak(),
        ]
    )
    return items


def full_evaluation() -> list[Flowable]:
    items = section_title(
        "07 / Full evaluation",
        "Run the complete split and inspect it",
        "Official R2 values and the composite score are calculated only after every case in the "
        "selected test split has completed. The requested Full baseline contains 50 test cases. "
        "The declared prediction scope applies consistently to every case in that entry.",
    )
    items.extend(
        [
            para("Run all cases", "h2"),
            code_block(
                """
autocfd5-aiml evaluate-entry my-entry \\
  --dataset-root /data/drivaerml \\
  --support-root support/native-v1 \\
  --output output/assigned-submission-id \\
  --resume
"""
            ),
            para(
                "If the process is interrupted, repeat the same command with <font name='Courier'>--resume</font>. "
                "Completed per-case work is reused only after its schema, case ID, and completion state pass validation. "
                "After <font name='Courier'>result.json</font> exists, that output is complete and immutable; use a new "
                "output directory for another model version.",
                "small",
            ),
            callout(
                "Existing full-field inference is reusable",
                "If you already produced complete v1.1.2 or v1.1.3 surface and volume prediction "
                "chunks, do not run model inference again. Keep those manifests and NPZ files, "
                "set <font name='Courier'>prediction_scope = surface_and_volume</font>, and rerun "
                "the v1.1.5 evaluator into a fresh output directory. Adding direct coefficients does not require rerunning field inference.",
            ),
            para("Output layout", "h2"),
            code_block(
                """
output/assigned-submission-id/
  result.json                 # aggregate metrics and identities
  regional-diagnostics.json   # zero-weight regional field reports
  provenance.json             # runtime and verification record
  cases/run_N.json            # compact result for each test case
  profiles/index.json         # profile prediction index
  profiles/chunk-NNN.json     # 40 series per case, eight cases per chunk
  direct-forces/run_N.json    # copied direct input, when direct route is selected
  .work/cases/run_N.json      # resumable working data; excluded from package
"""
            ),
            para("Render a local case report", "h2"),
            code_block(
                """
autocfd5-aiml report \\
  --result-root output/assigned-submission-id \\
  --support-root support/native-v1 \\
  --case-id run_11 \\
  --output output/run_11.html

# Open output/run_11.html in a browser on the same machine.
"""
            ),
            para("How to read the profile report", "h2"),
            data_table(
                ["Series", "Count/case", "Role", "Display and scoring behaviour"],
                [
                    ["Constant velocity", "16", "Scored if volume", "Raw U/U_inf samples for full entries; explicitly unavailable for surface-only."],
                    ["Relative velocity", "16", "Report only", "Full entries use the same numerical treatment; surface-only contains no prediction values."],
                    ["Constant continuous Cp", "4", "Scored", "Shown against physical x; integrated against arc length."],
                    ["Relative Cp", "4", "Report only", "Two aliases and two moving placements; zero composite weight."],
                ],
                [39 * mm, 21 * mm, 24 * mm, CONTENT_WIDTH - 84 * mm],
                compact=True,
            ),
            PageBreak(),
        ]
    )
    return items


def scoring() -> list[Flowable]:
    items = section_title(
        "08 / Scientific score",
        "Nine components, one approved composite",
        "The composite keeps the approved nine fixed weights. Nominally, fields contribute 50%, "
        "force coefficients 25%, and constant-placement profiles 25%. Entries use either field-integrated "
        "or explicitly declared direct coefficients under the same convention. Relative-placement profiles "
        "and regional field reports remain visible zero-weight diagnostics.",
    )
    items.extend(
        [
            data_table(
                ["Group", "Component metric", "Overall weight", "Transform / cap"],
                [
                    ["Fields", "Surface pressure relative L2, area weighted", "15%", "Error score; cap 15%"],
                    ["Fields", "Surface wall shear relative L2, area weighted", "10%", "Error score; cap 20%"],
                    ["Fields", "Volume velocity relative L2, equal native cells", "15%", "Error score; cap 12%"],
                    ["Fields", "Volume pressure relative L2, equal native cells", "10%", "Error score; cap 15%"],
                    ["Forces", "Cd R2", "15%", "Quality score"],
                    ["Forces", "Cl R2", "5%", "Quality score"],
                    ["Forces", "Pitch-moment R2", "5%", "Quality score"],
                    ["Profiles", "16 constant velocity profiles: global weighted R2", "15%", "Quality score"],
                    ["Profiles", "4 constant continuous Cp cuts: global weighted R2", "10%", "Quality score"],
                ],
                [24 * mm, 77 * mm, 24 * mm, CONTENT_WIDTH - 125 * mm],
                compact=True,
            ),
            callout(
                "Surface-only scoring: fixed 60-point ceiling",
                "Surface pressure, wall shear, all three force components, and Cp "
                "remain available: together their fixed weights total 60%. Volume velocity (15%), "
                "volume pressure (10%), and constant velocity profiles (15%) are unavailable and each "
                "receives a transformed component score of exactly zero. Their scientific metric values "
                "are absent, no dummy fields are used, and no weight is transferred to another component. "
                "A perfect surface-only entry therefore scores 60/100.",
                tone="orange",
            ),
            para("Transforms", "h2"),
            callout(
                "Field-error component",
                "For relative L2 error <i>e</i> and declared cap <i>c</i>: "
                "<b>score = clip(100 x (1 - e/c), 0, 100)</b>.",
            ),
            callout(
                "R2 component",
                "For complete-split coefficient of determination R2: "
                "<b>score = 100 x clip(R2, 0, 1)</b>. The weighted component scores sum to the overall score.",
            ),
            para("Important scientific details", "h2"),
            bullet("Available field errors are complete-case relative L2 percentages, macro-averaged equally across cases."),
            bullet("Forces are integrated from predicted native surface pressure and wall shear. Pitch truth is <font name='Courier'>(Clf - Clr) / 2</font>."),
            bullet("Velocity is <font name='Courier'>magnitude(UMeanTrim) / 38.889</font>. Cp is <font name='Courier'>2 * pMeanTrim / 38.889^2</font>."),
            bullet("Profile integration follows each scoring coordinate. Every case/profile block is normalized to unit supported length, giving cases and profiles equal weight in global R2."),
            bullet("Integration stops at every segment boundary. No unsupported interval is bridged and no smoothing is applied."),
            bullet("Four-region surface reports, plus volume reports when submitted, reuse native-cell fields. They have weight 0.0 and are not consumed by any transformed component or the overall score."),
            PageBreak(),
        ]
    )
    return items


def delivery() -> list[Flowable]:
    items = section_title(
        "09 / Package and delivery",
        "Verify first; upload privately",
        "The packaged result is compact and deterministic. It contains the declared scope, available "
        "scientific outputs, component availability and scores, available profile predictions, "
        "report-only regional diagnostics, entry identity, immutable input hashes, and runtime provenance - not the "
        "large raw native prediction chunks by default.",
    )
    items.extend(
        [
            para("Create the result package", "h2"),
            code_block(
                """
autocfd5-aiml package output/assigned-submission-id \\
  --output assigned-submission-id.zip

autocfd5-aiml verify-package assigned-submission-id.zip
"""
            ),
            para(
                "Replace <font name='Courier'>assigned-submission-id</font> with the exact ID sent by the "
                "AutoCFD organising committee. Packaging also writes "
                "<font name='Courier'>assigned-submission-id.zip.sha256</font>. Both commands "
                "refuse unsafe or inconsistent content. The ZIP is closed by "
                "<font name='Courier'>package-manifest.json</font>, which records every member's size and SHA-256.",
            ),
            para("Private hand-in", "h2"),
            numbered(
                1,
                f'<link href="{DROPBOX_REQUEST_URL}"><b>Open the AutoCFD Dropbox File Request</b></link>.',
            ),
            numbered(2, "Upload only <font name='Courier'>assigned-submission-id.zip</font>; wait for the upload to complete."),
            numbered(3, "Retain the original ZIP and its generated <font name='Courier'>.sha256</font> file unchanged."),
            numbered(4, "Email the organisers the receipt details below. Do not attach the ZIP to email."),
            numbered(5, "Keep predictions, results, and reports out of public Git history and issue trackers."),
            callout(
                "What the upload-only request protects",
                "Participants can add their own file but cannot browse, download, replace, or compare "
                "other participants' submissions. Organisers keep the destination restricted to the processing "
                "group until the workshop reveal.",
                tone="orange",
            ),
            para("Checksum receipt email", "h2"),
            code_block(
                """
Subject: [AutoCFD5 AIML] entry receipt - <submission-id>

Submission ID: <submission-id>
Method: <method-name>
Uploaded filename: <submission-id>.zip
SHA-256: <copy the 64-character value from <submission-id>.zip.sha256>
Upload completed: <YYYY-MM-DD HH:MM UTC>
Contact: <contact-email>
"""
            ),
            para("Optional large prediction artifact", "h2"),
            para(
                "Only when requested, store large native predictions at a private immutable URL and add "
                "<font name='Courier'>prediction_artifact</font> to <font name='Courier'>entry.json</font> with "
                "exact <font name='Courier'>private_immutable_url</font>, <font name='Courier'>size_bytes</font>, "
                "and <font name='Courier'>sha256</font>. The evaluator records the reference but does not copy "
                "that artifact into the result ZIP.",
            ),
            para(
                'Questions: <link href="mailto:neil@neilashton.co.uk">neil@neilashton.co.uk</link> or '
                '<link href="mailto:astridwalle@cfdsolutions.net">astridwalle@cfdsolutions.net</link>, '
                "the AutoCFD5 AI/ML TFG organisers.",
                "small",
            ),
            PageBreak(),
        ]
    )
    return items


def troubleshooting() -> list[Flowable]:
    items = section_title(
        "10 / Before you submit",
        "Troubleshooting and final checks",
        "Most failures are deliberate fail-closed checks. Correct the input or choose a fresh output "
        "location; do not edit a completed result package by hand.",
    )
    items.extend(
        [
            data_table(
                ["Message or symptom", "What it means / what to do"],
                [
                    ["required command is unavailable", "Install the named <font name='Courier'>gh</font> or <font name='Courier'>hf</font> CLI and confirm it is on PATH."],
                    ["support destination is not empty", "Use a new empty directory. Support extraction is intentionally non-overwriting."],
                    ["archive, index, or native source differs", "The file is not the pinned object. Re-fetch into a clean location and do not rename, recompress, or edit it."],
                    ["entry split ID, order or membership differs", "For an official split, restore its complete ordered test list. For a custom split, supply complete, disjoint train, validation, and test arrays."],
                    ["prediction manifest or chunk identity differs", "Regenerate manifest sizes and SHA-256 values after writing final NPZ chunks. Do not modify chunks afterward."],
                    ["raw IDs are missing, repeated, or out of range", "Export every native cell exactly once. Do not use solver-local reorderings without mapping back to raw native IDs."],
                    ["volume manifest is required", "The entry is using <font name='Courier'>surface_and_volume</font> (also the legacy default). Supply complete volume predictions or explicitly set <font name='Courier'>prediction_scope</font> to <font name='Courier'>surface_only</font>."],
                    ["surface-only entry contains no velocity metric", "Expected: velocity-profile and both volume scientific metrics are absent; their component scores are zero and weights stay fixed."],
                    ["result.json already exists", "That output directory is complete. Choose a new output directory for another model version."],
                    ["interrupted full evaluation", "Repeat the identical command with <font name='Courier'>--resume</font>; validated completed case work is retained."],
                    ["profile line appears stepped or has a gap", "This can be scientifically correct: raw samples are unsmoothed, and unsupported intervals are intentionally disconnected."],
                    ["temporary space is exhausted", "For full-field entries, the volume-region pass needs roughly 9 GiB of temporary local space per active case. Point <font name='Courier'>TMPDIR</font> at suitable local scratch or reduce evaluation concurrency. Surface-only never opens volume data."],
                    ["regional diagnostics do not reconstruct", "Do not edit the report. Re-run with the frozen evaluator and unchanged prediction chunks; all four exhaustive regions must reproduce the global additive field sums."],
                ],
                [48 * mm, CONTENT_WIDTH - 48 * mm],
                compact=True,
            ),
            para("Final participant checklist", "h2"),
            bullet(f"[ ] I used Linux, Python 3.12, and the frozen <b>{EVALUATOR_TAG}</b> release."),
            bullet("[ ] The support and native dataset identities verified automatically."),
            bullet("[ ] My <font name='Courier'>entry.json</font> uses the submission ID sent by the AutoCFD organising committee and the official Full split."),
            bullet("[ ] I declared one prediction scope. Every selected case has the complete native surface; full-field entries also have the complete native volume."),
            bullet("[ ] I declared the force route. If direct coefficients are selected, every test case has an exact constant-reference Cd, Clf, and Clr file."),
            bullet("[ ] <font name='Courier'>evaluate-entry</font> completed and <font name='Courier'>result.json</font> reports the exact split as complete."),
            bullet("[ ] I inspected aggregate metrics and at least one local HTML report; any unavailable surface-only components are explicitly marked and contain no dummy values."),
            bullet("[ ] I confirmed regional diagnostics are report only, have weight 0.0, and reconstruct every submitted field's unchanged global sums."),
            bullet("[ ] <font name='Courier'>verify-package</font> reported the final ZIP as valid."),
            bullet("[ ] I uploaded the ZIP through the AutoCFD Dropbox File Request and retained the original ZIP plus checksum."),
            bullet("[ ] My receipt email contains the exact submission ID, filename, and SHA-256."),
        ]
    )
    return items


def build(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    story: list[Flowable] = []
    for section in (
        cover_story,
        start_here,
        split_choices,
        setup_and_inputs,
        entry_metadata,
        prediction_format,
        development_test,
        full_evaluation,
        scoring,
        delivery,
        troubleshooting,
    ):
        story.extend(section())
    document = GuideDocTemplate(str(output))
    document.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/AutoCFD5_AIML_Submission_Instructions.pdf"),
    )
    args = parser.parse_args()
    build(args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
