import unittest

from app.load_assist import (
    LOAD_ASSIST_SERVICE_TYPE,
    TERMS_AND_EXCLUSIONS,
    PricingConfig,
    build_load_assist_payload,
    calculate_service_fare,
    create_driver_handoff,
    is_add_on_available,
    validate_load_assist_payload,
)


class LoadAssistTests(unittest.TestCase):
    def valid_payload(self):
        return build_load_assist_payload(
            vehicle_category="pickup_truck",
            selected=True,
            pickup_is_ground_floor=False,
            pickup_lift_available=False,
            pickup_floor_number=4,
            drop_is_ground_floor=False,
            drop_lift_available=True,
            drop_floor_number=2,
            goods_type="Office boxes",
            item_count=3,
            customer_notes="Bring trolley if available.",
        )

    def test_pickup_truck_booking_shows_add_on(self):
        self.assertTrue(is_add_on_available("pickup_truck"))
        self.assertTrue(is_add_on_available(" PICKUP_TRUCK "))

    def test_non_pickup_booking_hides_add_on(self):
        self.assertFalse(is_add_on_available("bike"))
        self.assertFalse(is_add_on_available("mini_truck"))

    def test_selected_add_on_requires_structured_details(self):
        payload = build_load_assist_payload(
            vehicle_category="pickup_truck",
            selected=True,
            goods_type="Boxes",
            item_count=2,
        )

        result = validate_load_assist_payload(payload)

        self.assertFalse(result.is_valid)
        self.assertIn("pickup.isGroundFloor must be true or false.", result.errors)
        self.assertIn("drop.isGroundFloor must be true or false.", result.errors)

    def test_free_text_notes_are_optional_but_saved(self):
        payload = build_load_assist_payload(
            vehicle_category="pickup_truck",
            selected=True,
            pickup_is_ground_floor=True,
            drop_is_ground_floor=True,
            goods_type="Cartons",
            item_count=1,
        )

        result = validate_load_assist_payload(payload)
        handoff = create_driver_handoff(payload)

        self.assertTrue(result.is_valid)
        self.assertEqual(handoff["customerNotes"], "")

        payload_with_notes = self.valid_payload()
        handoff_with_notes = create_driver_handoff(payload_with_notes)
        self.assertEqual(handoff_with_notes["customerNotes"], "Bring trolley if available.")

    def test_fare_changes_after_add_on_selection(self):
        pricing = PricingConfig(
            base_service_fee=100,
            per_item_rate=7,
            per_floor_rate=10,
            no_lift_floor_surcharge=20,
        )
        unselected = build_load_assist_payload(vehicle_category="pickup_truck", selected=False)

        selected_fare = calculate_service_fare(self.valid_payload(), pricing)
        unselected_fare = calculate_service_fare(unselected, pricing)

        self.assertEqual(unselected_fare.service_fare, 0)
        self.assertGreater(selected_fare.service_fare, 0)
        self.assertEqual(selected_fare.service_fare, 201)

    def test_booking_summary_contains_loading_unloading_details(self):
        handoff = create_driver_handoff(self.valid_payload())

        self.assertTrue(handoff["loadAssistSelected"])
        self.assertEqual(handoff["serviceType"], LOAD_ASSIST_SERVICE_TYPE)
        self.assertEqual(handoff["pickup"]["floorNumber"], 4)
        self.assertEqual(handoff["drop"]["floorNumber"], 2)
        self.assertEqual(handoff["itemCount"], 3)

    def test_terms_and_exclusions_are_available(self):
        terms = " ".join(TERMS_AND_EXCLUSIONS).lower()

        self.assertIn("packaging", terms)
        self.assertIn("assembly", terms)
        self.assertIn("dismantling", terms)
        self.assertIn("rope pulling", terms)
        self.assertIn("technical assistance", terms)

    def test_customer_cannot_book_prohibited_goods(self):
        heavy_payload = build_load_assist_payload(
            vehicle_category="pickup_truck",
            selected=True,
            pickup_is_ground_floor=True,
            drop_is_ground_floor=True,
            goods_type="Commercial appliance",
            item_count=1,
            max_item_weight_kg=55,
        )
        large_item_payload = build_load_assist_payload(
            vehicle_category="pickup_truck",
            selected=True,
            pickup_is_ground_floor=True,
            drop_is_ground_floor=True,
            goods_type="King size cot",
            item_count=1,
        )

        self.assertFalse(validate_load_assist_payload(heavy_payload).is_valid)
        self.assertFalse(validate_load_assist_payload(large_item_payload).is_valid)

    def test_selected_service_is_only_valid_for_pickup_truck(self):
        payload = self.valid_payload()
        payload["vehicleCategory"] = "bike"

        result = validate_load_assist_payload(payload)

        self.assertFalse(result.is_valid)
        self.assertIn("Loading/unloading is available only for pickup truck bookings.", result.errors)


if __name__ == "__main__":
    unittest.main()
