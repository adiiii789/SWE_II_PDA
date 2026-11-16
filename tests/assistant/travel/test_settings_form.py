"""Reise-Einstellungen im Popup (settings.py) und wie TravelSettings sie liest."""
import unittest
from dataclasses import fields

from backend.assistant.settings import SETTINGS_KEYS, TRAVEL_KEY
from backend.assistant.skills.travel.planner import HOME_ADDRESS, TravelSettings
from backend.assistant.skills.travel.settings import GROUPS, HOME, TravelSettingsForm
from tests.assistant.test_settings import MemoryStore


class TravelSettingsFormTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.form = TravelSettingsForm(self.store, lambda: {"ors": True, "rail": False})

    def group(self, form, group_id):
        return next(group for group in form if group["id"] == group_id)

    def test_every_setting_has_a_field_and_valid_default(self):
        keys = {setting.key for group in GROUPS for setting in group.settings}
        self.assertEqual(keys - {HOME}, {f.name for f in fields(TravelSettings)})
        for group in GROUPS:
            for setting in group.settings:
                with self.subTest(key=setting.key):
                    self.assertEqual(setting.clean(setting.default), setting.default)

    def test_form_shows_defaults_and_missing_services(self):
        form = self.form.form()
        self.assertEqual([group["id"] for group in form],
                         ["general", "transit", "car", "bike_walk", "weather", "reminder", "fares"])
        self.assertEqual(self.group(form, "reminder")["values"]["reminder_minutes"], 15)
        self.assertEqual(self.group(form, "transit")["values"]["train_transfers"], "2")
        self.assertTrue(self.group(form, "transit")["available"])   # Bus und Bahn ohne DB-Keys
        self.assertTrue(self.group(form, "weather")["available"])   # braucht keinen Key
        general = self.group(form, "general")["values"]
        self.assertEqual((general["modes"], general["prefer_free"]), (["train", "bike", "foot", "car", "taxi"], True))
        step = next(f for f in self.group(form, "car")["fields"] if f["key"] == "consumption")["step"]
        self.assertEqual(step, 0.1)

    def test_save_and_read_back(self):
        values = self.form.validated({"general": {HOME: "Hauptstraße 1, Mannheim", "value_of_time": 40,
                                                  "modes": ["foot", "train"], "prefer_free": False},
                                      "transit": {"train_transfers": "0"}, "fares": {"rail_min_fare": 3.45},
                                      "car": {"fuel": "diesel", "consumption": 6.5}})
        self.assertEqual(self.store.values, {})   # erst store_validated schreibt
        self.form.store_validated(values)
        settings = TravelSettings.from_preferences(self.store)
        self.assertEqual((settings.value_of_time, settings.train_transfers, settings.rail_min_fare),
                         (40.0, 0, 3.45))
        self.assertEqual((settings.fuel, settings.consumption), ("diesel", 6.5))
        self.assertEqual((settings.modes, settings.prefer_free), (("train", "foot"), False))   # feste Reihenfolge
        self.assertEqual(self.store.get(HOME_ADDRESS), "Hauptstraße 1, Mannheim")
        self.assertNotIn(HOME, self.store.get(TRAVEL_KEY))
        self.assertEqual(self.group(self.form.form(), "general")["values"][HOME], "Hauptstraße 1, Mannheim")

    def test_popup_wins_over_hand_written_values(self):
        self.store.set("travel_value_of_time", 40)
        self.assertEqual(self.group(self.form.form(), "general")["values"]["value_of_time"], 40.0)
        self.form.store_validated(self.form.validated({"general": {"value_of_time": 30}}))
        self.assertEqual(TravelSettings.from_preferences(self.store).value_of_time, 30.0)

    def test_invalid_values(self):
        for changes in ({"nirgends": {}}, {"car": {"fuel": "kerosin"}}, {"car": {"consumption": 99}},
                        {"general": {"unbekannt": 1}}, {"general": {"modes": ["rakete"]}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.form.validated(changes)
        self.assertIsNone(self.form.validated(None))
        self.form.store_validated(None)
        self.assertEqual(self.store.values, {})

    def test_reset_keeps_home_address(self):
        self.form.store_validated(self.form.validated({"general": {HOME: "Daheim", "buffer_minutes": 20}}))
        self.form.reset()
        self.assertEqual(TravelSettings.from_preferences(self.store), TravelSettings())
        self.assertEqual(self.store.get(HOME_ADDRESS), "Daheim")

    def test_settings_are_not_sent_to_the_model(self):
        self.assertIn(TRAVEL_KEY, SETTINGS_KEYS)

    def test_broken_stored_values_fall_back(self):
        self.store.set(TRAVEL_KEY, "kaputt")
        self.assertEqual(TravelSettings.from_preferences(self.store), TravelSettings())
        self.store.set(TRAVEL_KEY, {"consumption": "viel", "reminder": 1})
        settings = TravelSettings.from_preferences(self.store)
        self.assertEqual(settings.consumption, 7.0)
        self.assertIs(settings.reminder, True)


if __name__ == "__main__":
    unittest.main()
