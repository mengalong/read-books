from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, ContentChunk, PdfDocument
from app.config import PROJECT_ROOT


DEMO_PAGES = [
    (
        8,
        "遗忘并不是记忆出了故障，而是大脑在主动筛选信息。一次阅读留下的痕迹会快速变淡，"
        "如果只重新浏览熟悉的句子，人很容易把熟悉感误认为真正掌握。有效复习需要把信息从记忆中主动提取出来。",
    ),
    (
        15,
        "主动回忆是合上书本之后，尝试用自己的语言复述观点、过程和例子。提取时感到吃力并不意味着学习失败；"
        "恰当的困难会强化记忆线索，使下一次回想更容易。",
    ),
    (
        23,
        "间隔复习的关键不是固定地重复同一内容，而是在即将遗忘时再次尝试回忆。"
        "掌握较弱的内容应较早出现，已经稳定掌握的内容可以逐步拉长复习间隔。",
    ),
    (
        31,
        "一道好的复习题必须能追溯到阅读材料。题目、答案与解释都应有明确依据；"
        "当依据不足时，承认无法出题比用常识补全一个看似合理的答案更可靠。",
    ),
    (
        42,
        "选择题适合检查概念边界和事实辨认，但选项带来的提示会降低提取难度。"
        "问答题要求读者自行组织语言，更能暴露理解中的空白，因此两种题型应配合使用。",
    ),
    (
        56,
        "复习反馈不仅要给出分数，还要指出答案已经覆盖的要点和遗漏的要点。"
        "分数回答表现如何，具体反馈才回答下一步应该复习什么。",
    ),
    (
        68,
        "相同题目在短期内反复出现，测到的可能只是对题目的熟悉。改变提问角度、题型和材料位置，"
        "同时保留同一个核心知识点，才能更接近对知识迁移能力的检查。",
    ),
    (
        79,
        "一次日常复习不宜过长。十五分钟左右的测试足以完成若干次有效提取，也更容易成为稳定习惯。"
        "持续的小剂量练习通常比临时安排一次很长的复习更可执行。",
    ),
]


def seed_demo_data(db: Session) -> None:
    project_pdfs = sorted(PROJECT_ROOT.glob("*.pdf"))
    if project_pdfs:
        import_project_pdf(db, project_pdfs[0])
        return

    exists = db.scalar(select(Book.id).where(Book.title == "记忆与阅读：一份练习样稿"))
    if exists:
        return

    book = Book(
        title="记忆与阅读：一份练习样稿",
        author="回卷编辑部",
        description="用于体验完整复习流程的原创演示材料，可以直接生成测试。",
        cover_color="#D65A42",
        language="中文",
        reading_status="reviewing",
        tags=["学习方法", "演示书籍"],
    )
    db.add(book)
    db.flush()

    pdf = PdfDocument(
        book_id=book.id,
        file_name="记忆与阅读-演示样稿.pdf",
        file_path="demo://memory-and-reading",
        file_size=128_640,
        page_count=86,
        chunk_count=len(DEMO_PAGES),
        parse_status="completed",
    )
    db.add(pdf)
    db.flush()

    for sequence, (page_number, content) in enumerate(DEMO_PAGES, start=1):
        db.add(
            ContentChunk(
                book_id=book.id,
                pdf_id=pdf.id,
                page_number=page_number,
                sequence=sequence,
                content=content,
                char_count=len(content),
            )
        )
    db.commit()


def import_project_pdf(db: Session, pdf_path: Path) -> None:
    book_title = "红楼梦"
    book = db.scalar(select(Book).where(Book.title == book_title))
    if not book:
        book = Book(
            title=book_title,
            author="曹雪芹",
            description="来自项目目录的本地 PDF，用于验证基于原文的复习测试流程。",
            cover_color="#8B3A3A",
            language="中文",
            reading_status="finished",
            tags=["古典文学", "本地 PDF"],
        )
        db.add(book)
        db.flush()

    existing = db.scalar(
        select(PdfDocument).where(
            PdfDocument.book_id == book.id, PdfDocument.file_name == pdf_path.name
        )
    )
    if existing:
        return

    db.add(
        PdfDocument(
            book_id=book.id,
            file_name=pdf_path.name,
            file_path=str(pdf_path.resolve()),
            file_size=pdf_path.stat().st_size,
            parse_status="pending",
        )
    )
    db.commit()
