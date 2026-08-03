from sqlalchemy import select

from app.database import SessionLocal
from app.models import Book, ContentChunk, PdfDocument, Quiz, User
from app.services.auth import create_user_with_workspace, get_personal_workspace


ADMIN_USERNAME = "admin-auth"
ADMIN_PASSWORD = "InitialAdmin1!"
ADMIN_NEW_PASSWORD = "ChangedAdmin2!"


def ensure_test_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == ADMIN_USERNAME)):
            return
        create_user_with_workspace(
            db,
            username=ADMIN_USERNAME,
            display_name="认证测试管理员",
            password=ADMIN_PASSWORD,
            role="admin",
            must_change_password=True,
        )
        db.commit()


def test_login_first_password_change_and_admin_user_management(client):
    ensure_test_admin()
    client.cookies.clear()

    login = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert login.json()["workspace"]["name"] == "认证测试管理员的工作空间"

    blocked = client.get("/api/admin/users")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = client.post(
        "/api/auth/change-password",
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": ADMIN_NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False

    created = client.post(
        "/api/admin/users",
        json={
            "username": "reader-one",
            "display_name": "第一位读者",
            "role": "user",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["username"] == "reader-one"
    assert body["user"]["workspace"]["name"] == "第一位读者的工作空间"
    assert body["temporary_password"]

    users = client.get("/api/admin/users")
    assert users.status_code == 200
    assert {item["username"] for item in users.json()} >= {
        ADMIN_USERNAME,
        "reader-one",
    }

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_failed_login_does_not_create_session(client):
    ensure_test_admin()
    client.cookies.clear()
    response = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": "WrongPassword1!"},
    )
    assert response.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_workspace_data_is_private_for_users_and_visible_to_admin(client):
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "TestAdmin1!"},
    )
    assert admin_login.status_code == 200
    admin_book = client.post("/api/books", json={"title": "管理员工作空间的书"})
    assert admin_book.status_code == 201
    admin_book_id = admin_book.json()["id"]
    created = client.post(
        "/api/admin/users",
        json={
            "username": "isolated-reader",
            "display_name": "隔离测试读者",
            "temporary_password": "ReaderTemp1!",
        },
    )
    assert created.status_code == 201
    reader_id = created.json()["user"]["id"]

    client.post("/api/auth/logout")
    user_login = client.post(
        "/api/auth/login",
        json={"username": "isolated-reader", "password": "ReaderTemp1!"},
    )
    assert user_login.status_code == 200
    assert client.post(
        "/api/auth/change-password",
        json={"current_password": "ReaderTemp1!", "new_password": "ReaderNew2!"},
    ).status_code == 200
    book = client.post("/api/books", json={"title": "隔离工作空间的书"})
    assert book.status_code == 201
    book_id = book.json()["id"]
    assert client.get(f"/api/books/{admin_book_id}").status_code == 404

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "TestAdmin1!"},
    ).status_code == 200
    assert client.get(f"/api/books/{book_id}").status_code == 404
    assert all(item["id"] != book_id for item in client.get("/api/books").json())
    assert client.get(f"/api/books?owner_id={reader_id}").status_code == 403
    assert client.get(f"/api/admin/books/{book_id}").status_code == 200
    filtered_books = client.get(f"/api/admin/books?owner_id={reader_id}")
    assert filtered_books.status_code == 200
    assert [item["id"] for item in filtered_books.json()] == [book_id]
    assert client.patch(f"/api/books/{book_id}", json={"title": "越权修改"}).status_code == 404
    assert client.delete(f"/api/books/{book_id}").status_code == 404
    assert client.get(f"/api/admin/books/{book_id}").json()["title"] == "隔离工作空间的书"

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "isolated-reader", "password": "ReaderNew2!"},
    ).status_code == 200
    assert client.get(f"/api/books/{book_id}").status_code == 200


def test_admin_can_copy_book_content_without_copying_quizzes(client):
    with SessionLocal() as db:
        source_user, source_workspace = create_user_with_workspace(
            db,
            username="copy-source",
            display_name="复制来源用户",
            password="CopySource1!",
        )
        target_user, target_workspace = create_user_with_workspace(
            db,
            username="copy-target",
            display_name="复制目标用户",
            password="CopyTarget1!",
        )
        source_book = Book(
            title="可共享的书",
            author="测试作者",
            workspace_id=source_workspace.id,
            created_by_user_id=source_user.id,
        )
        db.add(source_book)
        db.flush()
        source_pdf = PdfDocument(
            book_id=source_book.id,
            file_name="source.pdf",
            file_path="demo://source.pdf",
            file_size=1024,
            page_count=1,
            chunk_count=1,
            parse_status="completed",
        )
        db.add(source_pdf)
        db.flush()
        db.add(
            ContentChunk(
                book_id=source_book.id,
                pdf_id=source_pdf.id,
                page_number=1,
                sequence=1,
                content="这是用于验证复制的原文片段。",
                char_count=14,
            )
        )
        db.add(Quiz(book_id=source_book.id, title="不应被复制的试卷"))
        db.commit()
        source_book_id = source_book.id
        target_user_id = target_user.id
        target_workspace_id = target_workspace.id

    response = client.post(
        f"/api/admin/books/{source_book_id}/copy",
        json={
            "target_user_id": target_user_id,
            "copy_pdf": True,
            "copy_content": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["copied_pdf_count"] == 1
    assert body["copied_chunk_count"] == 1
    assert body["book"]["workspace_id"] == target_workspace_id
    assert body["book"]["owner_user_id"] == target_user_id
    assert body["book"]["quizzes"] == []

    with SessionLocal() as db:
        copied_book = db.get(Book, body["book"]["id"])
        assert copied_book is not None
        assert copied_book.workspace_id == get_personal_workspace(db, target_user_id).id
        assert len(copied_book.pdfs) == 1
        assert len(copied_book.chunks) == 1
        assert copied_book.quizzes == []
