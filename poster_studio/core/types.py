"""
poster_studio.core.types
~~~~~~~~~~~~~~~~~~~~~~~~
Core geometric, bounding box, and layout primitive types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Tuple, Union


@dataclass(frozen=True)
class Point:
    """Represents a 2D coordinate point."""
    x: float
    y: float

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y


@dataclass(frozen=True)
class Size:
    """Represents 2D dimensions (width, height)."""
    width: int
    height: int

    def as_tuple(self) -> Tuple[int, int]:
        return (self.width, self.height)

    def __iter__(self) -> Iterator[int]:
        yield self.width
        yield self.height


@dataclass(frozen=True)
class Box:
    """
    Immutable representation of an axis-aligned bounding box.
    Coordinates are defined in (left, top, right, bottom) order.
    Supports iteration / unpacking as a 4-tuple (left, top, right, bottom).
    """
    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def from_ltrb(cls, left: int, top: int, right: int, bottom: int) -> Box:
        """Constructs a Box from explicit left, top, right, bottom coordinates."""
        return cls(left=int(left), top=int(top), right=int(right), bottom=int(bottom))

    @classmethod
    def from_xywh(cls, x: int, y: int, width: int, height: int) -> Box:
        """Constructs a Box from (x, y, width, height)."""
        x_int = int(x)
        y_int = int(y)
        w_int = int(width)
        h_int = int(height)
        return cls(left=x_int, top=y_int, right=x_int + w_int, bottom=y_int + h_int)

    @classmethod
    def from_any(cls, val: Union[Box, Tuple[int, int, int, int]]) -> Box:
        """Coerces a Box or 4-tuple into a Box object."""
        if isinstance(val, Box):
            return val
        if isinstance(val, (tuple, list)) and len(val) == 4:
            p0, p1, p2, p3 = val
            # Check if clearly (x, y, w, h) vs (left, top, right, bottom)
            # When p2 > p0 and p3 > p1, it could be either; but standard convention in our engine is LTRB.
            return cls.from_ltrb(p0, p1, p2, p3)
        raise TypeError(f"Cannot coerce {type(val).__name__} to Box: {val!r}")

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def x(self) -> int:
        return self.left

    @property
    def y(self) -> int:
        return self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    def as_ltrb(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def as_xywh(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)

    def contains(self, px: float, py: float) -> bool:
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def __iter__(self) -> Iterator[int]:
        """Allows unpacking: l, t, r, b = box"""
        yield self.left
        yield self.top
        yield self.right
        yield self.bottom

    def __getitem__(self, idx: int) -> int:
        return (self.left, self.top, self.right, self.bottom)[idx]
