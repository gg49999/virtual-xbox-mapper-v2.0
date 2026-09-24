"""Common page scaffolding: header (title, subtitle, actions) + content."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame

from ui.widgets import label


class Page(QWidget):
    def __init__(self, title: str, subtitle: str = "", scroll: bool = False, max_width: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(32, 22, 32, 14)
        hl.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = label(title, "pageTitle")
        titles.addWidget(self.title_label)
        self.subtitle_label = label(subtitle, "body2", wrap=True)
        self.subtitle_label.setVisible(bool(subtitle))
        titles.addWidget(self.subtitle_label)
        hl.addLayout(titles, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        hl.addLayout(self.actions)
        outer.addWidget(header)

        self.banner_area = QVBoxLayout()
        self.banner_area.setContentsMargins(32, 0, 32, 0)
        outer.addLayout(self.banner_area)

        if scroll:
            area = QScrollArea()
            area.setObjectName("pageScroll")
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body = QWidget()
            body.setObjectName("pageScrollBody")
            wrap = QHBoxLayout(body)
            wrap.setContentsMargins(32, 4, 32, 32)
            inner = QWidget()
            inner.setObjectName("pageScrollBody")
            if max_width:
                inner.setMaximumWidth(max_width)
            self.content = QVBoxLayout(inner)
            self.content.setContentsMargins(0, 0, 0, 0)
            self.content.setSpacing(16)
            wrap.addWidget(inner)
            if max_width:
                wrap.addStretch()
            area.setWidget(body)
            outer.addWidget(area, 1)
            self.scroll_area = area
        else:
            body = QWidget()
            self.content = QVBoxLayout(body)
            self.content.setContentsMargins(32, 4, 32, 24)
            self.content.setSpacing(16)
            outer.addWidget(body, 1)
            self.scroll_area = None

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def on_show(self) -> None:
        """Called when the page becomes visible."""

    def refresh_live(self) -> None:
        """Called on the UI refresh timer while the page is visible."""
