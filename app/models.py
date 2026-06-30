"""
Modele ORM sklepu.

Struktura jest podzbiorem docelowego schematu całego demonstratora
(stores / departments / products + zamówienia), tak aby później łatwo
dołożyć tabele klientów, sesji, klastrów i rekomendacji.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from .database import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True)
    slug = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    tagline = Column(String(160))
    currency = Column(String(8), default="PLN")
    theme = Column(String(40), default="dynamic")

    departments = relationship("Department", back_populates="store", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="store", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="store", cascade="all, delete-orphan")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    slug = Column(String(40), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    icon = Column(String(40))
    color = Column(String(16))
    description = Column(Text)
    position = Column(Integer, default=0)

    store = relationship("Store", back_populates="departments")
    products = relationship("Product", back_populates="department")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)

    sku = Column(String(24), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    brand = Column(String(80), index=True)
    category = Column(String(120), index=True)
    variant = Column(String(80))
    description = Column(Text)
    tags = Column(Text)
    icon = Column(String(40))
    color = Column(String(16))
    image_filename = Column(String(120))   # prawdziwe zdjęcie produktu (np. product_001.png)

    price = Column(Float, nullable=False)
    old_price = Column(Float, nullable=True)
    is_promo = Column(Boolean, default=False)
    stock = Column(Integer, default=0)
    rating = Column(Float, default=0)
    reviews = Column(Integer, default=0)

    store = relationship("Store", back_populates="products")
    department = relationship("Department", back_populates="products")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "department": self.department.slug if self.department else None,
            "department_name": self.department.name if self.department else None,
            "variant": self.variant,
            "description": self.description,
            "tags": [t for t in (self.tags or "").split(",") if t],
            "color": self.color,
            "price": self.price,
            "old_price": self.old_price,
            "is_promo": self.is_promo,
            "stock": self.stock,
            "rating": self.rating,
            "reviews": self.reviews,
            "image_filename": self.image_filename,
            "image": f"/api/products/{self.id}/image",
        }


class Order(Base):
    """Uproszczone, symulowane zamówienie (BEZ realnej płatności).

    Zapisujemy je, aby w przyszłości móc zasilić historię zakupów klienta
    w module rekomendacyjnym."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total = Column(Float, default=0)
    items_count = Column(Integer, default=0)
    status = Column(String(24), default="symulacja")

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    customer = relationship("Customer", back_populates="orders")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    name = Column(String(200))
    price = Column(Float)
    quantity = Column(Integer, default=1)

    order = relationship("Order", back_populates="items")

# ==========================================================================
# KLIENCI — archiwum / rejestr sprzedaży (segment B2C demonstratora)
# ==========================================================================
class Customer(Base):
    """Klient sklepu wraz z archiwum aktywności.

    Trzyma dane profilowe + zagregowane statystyki (liczba wizyt, zamówień,
    łączne wydatki), policzone przy seedowaniu dla szybkiego listowania.
    Szczegóły (zamówienia, wizyty, czaty) wiszą w relacjach poniżej."""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)

    full_name = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    phone = Column(String(32))
    city = Column(String(80))
    gender = Column(String(1))            # "k" / "m"
    age = Column(Integer)
    age_group = Column(String(10))               # "18-25" / "26-35" / "36-45" / "46-60" / "60+"
    affluence = Column(String(20))               # budżetowy / średni / zamożny / premium
    household = Column(String(40))               # singiel / para / rodzina z dziećmi / ...

    # Co go interesuje
    segment = Column(String(40), index=True)     # np. "Biegacz", "Siłownia", ...
    interest_summary = Column(Text)              # krótki opis zainteresowań
    favorite_department = Column(String(40))     # slug ulubionego działu
    favorite_brands = Column(Text)               # "Nike,Adidas" (CSV)

    # Jak często przychodził / lojalność
    loyalty_tier = Column(String(20), index=True)  # VIP / Stały / Regularny / Okazjonalny / Nowy
    created_at = Column(DateTime, default=datetime.utcnow)   # rejestracja / pierwsza wizyta
    last_visit_at = Column(DateTime)

    # Zagregowane statystyki (policzone przy seedowaniu)
    visits_count = Column(Integer, default=0)
    orders_count = Column(Integer, default=0)
    total_spent = Column(Float, default=0)

    newsletter = Column(Boolean, default=False)
    avatar_hue = Column(Integer, default=210)    # odcień HSL dla awatara w UI

    store = relationship("Store", back_populates="customers")
    orders = relationship("Order", back_populates="customer", order_by="Order.created_at")
    visits = relationship("Visit", back_populates="customer",
                          cascade="all, delete-orphan", order_by="Visit.visited_at")
    messages = relationship("ChatMessage", back_populates="customer",
                            cascade="all, delete-orphan", order_by="ChatMessage.created_at")

    @property
    def initials(self) -> str:
        parts = (self.full_name or "").split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    def as_card(self) -> dict:
        """Lekka reprezentacja na listę / menu wyboru tożsamości."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "initials": self.initials,
            "email": self.email,
            "city": self.city,
            "gender": self.gender,
            "age": self.age,
            "age_group": self.age_group,
            "affluence": self.affluence,
            "household": self.household,
            "segment": self.segment,
            "favorite_department": self.favorite_department,
            "loyalty_tier": self.loyalty_tier,
            "orders_count": self.orders_count,
            "visits_count": self.visits_count,
            "total_spent": round(self.total_spent or 0, 2),
            "last_visit_at": self.last_visit_at.isoformat() if self.last_visit_at else None,
            "avatar_hue": self.avatar_hue,
        }

    def as_dict(self) -> dict:
        d = self.as_card()
        d.update({
            "phone": self.phone,
            "interest_summary": self.interest_summary,
            "favorite_brands": [b for b in (self.favorite_brands or "").split(",") if b],
            "newsletter": self.newsletter,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        })
        return d


class Visit(Base):
    """Pojedyncza wizyta klienta w sklepie (sygnał częstotliwości i zainteresowań)."""
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    visited_at = Column(DateTime, nullable=False, index=True)
    department = Column(String(40))     # slug przeglądanego działu (lub None)
    source = Column(String(16))         # "web" / "mobile"
    converted = Column(Boolean, default=False)  # czy wizyta zakończyła się zakupem

    customer = relationship("Customer", back_populates="visits")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "visited_at": self.visited_at.isoformat() if self.visited_at else None,
            "department": self.department,
            "source": self.source,
            "converted": self.converted,
        }


class ChatMessage(Base):
    """Wiadomość z czatu/obsługi klienta — 'co pisali w chatach'."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, index=True)
    role = Column(String(12), default="klient")   # "klient" / "obsługa"
    topic = Column(String(24))                     # np. "dostawa", "rozmiar", "produkt"
    text = Column(Text, nullable=False)

    customer = relationship("Customer", back_populates="messages")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "role": self.role,
            "topic": self.topic,
            "text": self.text,
        }
