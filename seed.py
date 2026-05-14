"""
seed.py — Populate the database with sample data for development/testing.
Run: python seed.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.book import Book
from app.core.logger import logger


SAMPLE_USERS = [
    {
        "full_name": "Alice Admin",
        "email": "alice@library.com",
        "password": "Admin1234",
        "role": UserRole.admin,
    },
    {
        "full_name": "Bob Member",
        "email": "bob@library.com",
        "password": "Member1234",
        "role": UserRole.member,
    },
    {
        "full_name": "Carol Reader",
        "email": "carol@library.com",
        "password": "Member1234",
        "role": UserRole.member,
    },
]

SAMPLE_BOOKS = [
    {
        "title": "Clean Code",
        "author": "Robert C. Martin",
        "isbn": "978-0132350884",
        "genre": "Technology",
        "description": "A handbook of agile software craftsmanship.",
        "total_copies": 3,
        "published_year": 2008,
    },
    {
        "title": "The Pragmatic Programmer",
        "author": "David Thomas",
        "isbn": "978-0135957059",
        "genre": "Technology",
        "description": "Your journey to mastery.",
        "total_copies": 2,
        "published_year": 2019,
    },
    {
        "title": "Design Patterns",
        "author": "Gang of Four",
        "isbn": "978-0201633610",
        "genre": "Technology",
        "description": "Elements of reusable object-oriented software.",
        "total_copies": 2,
        "published_year": 1994,
    },
    {
        "title": "Dune",
        "author": "Frank Herbert",
        "isbn": "978-0441013593",
        "genre": "Science Fiction",
        "description": "A science fiction masterpiece.",
        "total_copies": 4,
        "published_year": 1965,
    },
    {
        "title": "1984",
        "author": "George Orwell",
        "isbn": "978-0451524935",
        "genre": "Dystopian Fiction",
        "description": "A dystopian social science fiction novel.",
        "total_copies": 3,
        "published_year": 1949,
    },
    {
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "isbn": "978-0743273565",
        "genre": "Classic Fiction",
        "description": "A story of wealth and obsession in the Jazz Age.",
        "total_copies": 2,
        "published_year": 1925,
    },
    {
        "title": "Atomic Habits",
        "author": "James Clear",
        "isbn": "978-0735211292",
        "genre": "Self-Help",
        "description": "An easy and proven way to build good habits.",
        "total_copies": 5,
        "published_year": 2018,
    },
    {
        "title": "Python Crash Course",
        "author": "Eric Matthes",
        "isbn": "978-1718502703",
        "genre": "Technology",
        "description": "A hands-on, project-based introduction to programming.",
        "total_copies": 3,
        "published_year": 2023,
    },
]


def seed():
    logger.info("Initializing database...")
    init_db()

    db = SessionLocal()
    try:
        # Seed users
        for u_data in SAMPLE_USERS:
            existing = db.query(User).filter(User.email == u_data["email"]).first()
            if not existing:
                user = User(
                    full_name=u_data["full_name"],
                    email=u_data["email"],
                    hashed_password=hash_password(u_data["password"]),
                    role=u_data["role"],
                )
                db.add(user)
                logger.info(f"  ✓ User: {u_data['email']} ({u_data['role']})")
            else:
                logger.info(f"  ↷ Skipped (exists): {u_data['email']}")

        db.commit()

        # Seed books
        for b_data in SAMPLE_BOOKS:
            existing = db.query(Book).filter(Book.isbn == b_data["isbn"]).first()
            if not existing:
                book = Book(
                    title=b_data["title"],
                    author=b_data["author"],
                    isbn=b_data["isbn"],
                    genre=b_data["genre"],
                    description=b_data.get("description"),
                    total_copies=b_data["total_copies"],
                    available_copies=b_data["total_copies"],
                    published_year=b_data.get("published_year"),
                )
                db.add(book)
                logger.info(f"  ✓ Book: '{b_data['title']}' by {b_data['author']}")
            else:
                logger.info(f"  ↷ Skipped (exists): '{b_data['title']}'")

        db.commit()
        logger.info("✅ Seeding complete!")
        print("\n📚 Library Management System — Seed Complete")
        print("─" * 45)
        print("Admin login:  alice@library.com / Admin1234")
        print("Member login: bob@library.com   / Member1234")
        print("Member login: carol@library.com / Member1234")
        print(f"\nAPI docs: http://localhost:8000/docs")

    except Exception as e:
        db.rollback()
        logger.error(f"Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
