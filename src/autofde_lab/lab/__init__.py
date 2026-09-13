"""Lab-scoped graduation packet capital (`V2030.1.1-PRD-ARD.md` capability 8).

See `autofde_lab.lab.graduation_packet` for the one type this package
currently exports, and its module docstring for how it relates to
`autofde_lab.reasoning.lab_standing.GraduationPacket` (capability 9's
falsification-lineage packet, a deliberately different type).
"""

from .graduation_packet import (
    PROMOTION_GRADUATION_SCHEMA,
    PromotionGraduationPacket,
    build_promotion_graduation_packet,
)

__all__ = [
    "PROMOTION_GRADUATION_SCHEMA",
    "PromotionGraduationPacket",
    "build_promotion_graduation_packet",
]
