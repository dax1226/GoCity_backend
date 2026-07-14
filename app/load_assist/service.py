"""Business logic for pickup truck loading/unloading add-on bookings.

This module is intentionally isolated from the Outlook automation app because
the current repository does not contain the real booking frontend/backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PICKUP_TRUCK_CATEGORY = "pickup_truck"
LOAD_ASSIST_SERVICE_TYPE = "loading_unloading"
MAX_CUSTOMER_NOTES_LENGTH = 500
MAX_ALLOWED_ITEM_WEIGHT_KG = 50

TERMS_AND_EXCLUSIONS = [
    "Packaging is not included.",
    "Assembly or disassembly is not included.",
    "Dismantling is not included.",
    "Rope pulling is not included.",
    "Technical assistance for appliances, machines, electronics, locking, or unlocking is not included.",
    "Goods heavier than the allowed service limit or not liftable by the assigned partners are prohibited.",
]

PROHIBITED_GOODS_KEYWORDS = (
    "king size cot",
    "queen size cot",
    "big wardrobe",
    "almirah",
    "5 seater sofa",
)


@dataclass(frozen=True)
class PricingConfig:
    """Configurable service fare inputs.

    The values here are defaults for this repository's standalone feature code.
    The real booking app should replace them with city/vehicle/business-rule
    based pricing.
    """

    base_service_fee: int = 50
    per_item_rate: int = 7
    per_floor_rate: int = 100
    no_lift_floor_surcharge: int = 150


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class FareBreakdown:
    service_fare: int
    line_items: tuple[dict[str, int | str], ...]


DEFAULT_PRICING = PricingConfig()


def is_add_on_available(vehicle_category: str | None) -> bool:
    """Return whether the loading/unloading add-on should be shown."""

    return (vehicle_category or "").strip().lower() == PICKUP_TRUCK_CATEGORY


def build_load_assist_payload(
    *,
    vehicle_category: str,
    selected: bool,
    pickup_is_ground_floor: bool | None = None,
    pickup_lift_available: bool | None = None,
    pickup_floor_number: int | None = None,
    drop_is_ground_floor: bool | None = None,
    drop_lift_available: bool | None = None,
    drop_floor_number: int | None = None,
    goods_type: str | None = None,
    item_count: int | None = None,
    customer_notes: str | None = None,
    max_item_weight_kg: float | None = None,
) -> dict[str, Any]:
    """Build the booking payload shape expected by the feature spec."""

    payload: dict[str, Any] = {
        "vehicleCategory": vehicle_category,
        "loadAssist": {
            "selected": selected,
        },
    }

    if not selected:
        return payload

    payload["loadAssist"].update(
        {
            "serviceType": LOAD_ASSIST_SERVICE_TYPE,
            "pickup": {
                "isGroundFloor": pickup_is_ground_floor,
                "liftAvailable": pickup_lift_available,
                "floorNumber": pickup_floor_number,
            },
            "drop": {
                "isGroundFloor": drop_is_ground_floor,
                "liftAvailable": drop_lift_available,
                "floorNumber": drop_floor_number,
            },
            "goodsType": (goods_type or "").strip(),
            "itemCount": item_count,
            "customerNotes": (customer_notes or "").strip(),
        }
    )

    if max_item_weight_kg is not None:
        payload["loadAssist"]["maxItemWeightKg"] = max_item_weight_kg

    return payload


def validate_load_assist_payload(payload: dict[str, Any]) -> ValidationResult:
    """Validate pickup truck loading/unloading details."""

    errors: list[str] = []
    vehicle_category = payload.get("vehicleCategory")
    load_assist = payload.get("loadAssist")

    if not isinstance(load_assist, dict):
        return ValidationResult(True, tuple())

    selected = load_assist.get("selected")
    if selected is not False and selected is not True:
        errors.append("loadAssist.selected must be true or false.")
        return ValidationResult(False, tuple(errors))

    if selected is False:
        return ValidationResult(True, tuple())

    if not is_add_on_available(vehicle_category):
        errors.append("Loading/unloading is available only for pickup truck bookings.")

    if load_assist.get("serviceType") != LOAD_ASSIST_SERVICE_TYPE:
        errors.append("loadAssist.serviceType must be loading_unloading.")

    _validate_location(errors, load_assist.get("pickup"), "pickup")
    _validate_location(errors, load_assist.get("drop"), "drop")

    goods_type = str(load_assist.get("goodsType") or "").strip()
    if not goods_type:
        errors.append("goodsType is required when loading/unloading is selected.")

    item_count = load_assist.get("itemCount")
    if not isinstance(item_count, int) or item_count <= 0:
        errors.append("itemCount must be a positive number when loading/unloading is selected.")

    customer_notes = str(load_assist.get("customerNotes") or "")
    if len(customer_notes) > MAX_CUSTOMER_NOTES_LENGTH:
        errors.append(f"customerNotes must be {MAX_CUSTOMER_NOTES_LENGTH} characters or fewer.")

    if _is_prohibited_goods(goods_type, load_assist.get("maxItemWeightKg")):
        errors.append("Goods are prohibited for loading/unloading service.")

    return ValidationResult(not errors, tuple(errors))


def calculate_service_fare(
    payload: dict[str, Any],
    pricing: PricingConfig = DEFAULT_PRICING,
) -> FareBreakdown:
    """Calculate a configurable service fare for the selected add-on."""

    load_assist = payload.get("loadAssist")
    if not isinstance(load_assist, dict) or load_assist.get("selected") is not True:
        return FareBreakdown(service_fare=0, line_items=tuple())

    validation = validate_load_assist_payload(payload)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))

    item_count = int(load_assist["itemCount"])
    pickup = load_assist["pickup"]
    drop = load_assist["drop"]
    floor_count = _billable_floor_count(pickup) + _billable_floor_count(drop)
    no_lift_locations = int(not pickup["isGroundFloor"] and not pickup["liftAvailable"]) + int(
        not drop["isGroundFloor"] and not drop["liftAvailable"]
    )

    line_items = (
        {"label": "Base loading/unloading service", "amount": pricing.base_service_fee},
        {"label": "Goods quantity charge", "amount": item_count * pricing.per_item_rate},
        {"label": "Floor handling charge", "amount": floor_count * pricing.per_floor_rate},
        {"label": "No-lift handling surcharge", "amount": no_lift_locations * pricing.no_lift_floor_surcharge},
    )
    return FareBreakdown(service_fare=sum(int(item["amount"]) for item in line_items), line_items=line_items)


def create_driver_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    """Create the driver/operations handoff summary for a selected add-on."""

    validation = validate_load_assist_payload(payload)
    if not validation.is_valid:
        raise ValueError("; ".join(validation.errors))

    load_assist = payload.get("loadAssist") or {}
    if load_assist.get("selected") is not True:
        return {"loadAssistSelected": False}

    return {
        "loadAssistSelected": True,
        "serviceType": load_assist["serviceType"],
        "pickup": dict(load_assist["pickup"]),
        "drop": dict(load_assist["drop"]),
        "goodsType": load_assist["goodsType"],
        "itemCount": load_assist["itemCount"],
        "customerNotes": load_assist.get("customerNotes", ""),
    }


def _validate_location(errors: list[str], location: Any, label: str) -> None:
    if not isinstance(location, dict):
        errors.append(f"{label} details are required.")
        return

    is_ground_floor = location.get("isGroundFloor")
    if is_ground_floor is not True and is_ground_floor is not False:
        errors.append(f"{label}.isGroundFloor must be true or false.")
        return

    if is_ground_floor is True:
        return

    lift_available = location.get("liftAvailable")
    if lift_available is not True and lift_available is not False:
        errors.append(f"{label}.liftAvailable must be true or false.")

    floor_number = location.get("floorNumber")
    if not isinstance(floor_number, int) or floor_number <= 0:
        errors.append(f"{label}.floorNumber must be a positive number when not on the ground floor.")


def _billable_floor_count(location: dict[str, Any]) -> int:
    if location["isGroundFloor"]:
        return 0
    return int(location["floorNumber"])


def _is_prohibited_goods(goods_type: str, max_item_weight_kg: Any) -> bool:
    normalized_goods = goods_type.lower()
    if any(keyword in normalized_goods for keyword in PROHIBITED_GOODS_KEYWORDS):
        return True

    if max_item_weight_kg is None:
        return False

    try:
        return float(max_item_weight_kg) > MAX_ALLOWED_ITEM_WEIGHT_KG
    except (TypeError, ValueError):
        return True
