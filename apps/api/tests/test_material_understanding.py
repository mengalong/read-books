from __future__ import annotations

from app.database import SessionLocal
from app.models import Book, MaterialSegment, MaterialUnderstanding, ResourceMaterial
from app.services.material_understanding import (
    get_understanding_context,
    refresh_material_understanding,
)


def _seed_book_with_segments(db, *, episode_texts: dict[int, list[str]]) -> str:
    book = Book(title="潜伏", author="姜伟", resource_type="tv_series")
    db.add(book)
    db.flush()
    material = ResourceMaterial(
        book_id=book.id,
        material_type="quote_sheet",
        file_format="csv",
        file_name="dialogues.csv",
        file_path="/tmp/dialogues.csv",
        file_hash="hash-1",
        parse_status="completed",
    )
    db.add(material)
    db.flush()
    sequence = 1
    for episode_number, lines in episode_texts.items():
        for line in lines:
            db.add(
                MaterialSegment(
                    book_id=book.id,
                    material_id=material.id,
                    sequence=sequence,
                    content=line,
                    content_hash=f"hash-{sequence}",
                    episode_number=episode_number,
                    speaker="余则成",
                )
            )
            sequence += 1
    db.commit()
    return book.id


def test_refresh_material_understanding_creates_scoped_and_book_summaries(client):
    with SessionLocal() as db:
        book_id = _seed_book_with_segments(
            db,
            episode_texts={
                1: ["余则成在阁楼调试监听设备。", "他听到林怀复谈论国共关系。"],
                2: ["李海丰叛逃，戴笠震怒。", "毛人凤汇报案情。"],
            },
        )

    refresh_material_understanding(book_id)

    with SessionLocal() as db:
        rows = list(
            db.query(MaterialUnderstanding).filter(MaterialUnderstanding.book_id == book_id).all()
        )
        scope_types = {row.scope_type for row in rows}
        assert "episode" in scope_types
        assert "book" in scope_types
        for row in rows:
            assert row.status == "completed"
            assert row.summary_text

        context = get_understanding_context(db, book_id, episode_numbers={1})
        assert "整体背景摘要" in context
        assert "第1集背景摘要" in context


def test_refresh_material_understanding_is_incremental_for_unchanged_scopes(client):
    with SessionLocal() as db:
        book_id = _seed_book_with_segments(
            db, episode_texts={1: ["余则成在阁楼调试监听设备。"]}
        )

    refresh_material_understanding(book_id)
    with SessionLocal() as db:
        first_episode_row = (
            db.query(MaterialUnderstanding)
            .filter(
                MaterialUnderstanding.book_id == book_id,
                MaterialUnderstanding.scope_type == "episode",
            )
            .one()
        )
        first_signature = first_episode_row.content_signature
        first_updated_at = first_episode_row.updated_at

    with SessionLocal() as db:
        material = db.query(ResourceMaterial).filter(ResourceMaterial.book_id == book_id).one()
        db.add(
            MaterialSegment(
                book_id=book_id,
                material_id=material.id,
                sequence=99,
                content="新增台词：这是后来补充的内容。",
                content_hash="hash-new",
                episode_number=2,
                speaker="吕宗方",
            )
        )
        db.commit()

    refresh_material_understanding(book_id)
    with SessionLocal() as db:
        episode_one_row = (
            db.query(MaterialUnderstanding)
            .filter(
                MaterialUnderstanding.book_id == book_id,
                MaterialUnderstanding.scope_type == "episode",
                MaterialUnderstanding.scope_ref == "1",
            )
            .one()
        )
        assert episode_one_row.content_signature == first_signature
        assert episode_one_row.updated_at == first_updated_at

        episode_two_row = (
            db.query(MaterialUnderstanding)
            .filter(
                MaterialUnderstanding.book_id == book_id,
                MaterialUnderstanding.scope_type == "episode",
                MaterialUnderstanding.scope_ref == "2",
            )
            .one()
        )
        assert episode_two_row.status == "completed"
