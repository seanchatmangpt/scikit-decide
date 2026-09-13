import importlib.util
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "autofde_admit_requirement.py"
)
SPEC = importlib.util.spec_from_file_location("autofde_admit_requirement", SCRIPT)
admit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(admit)


def requirement():
    return {
        "schema": "autofde.engineering-requirement/1",
        "standing": "BLOCKED:CAPABILITY_ABSENT",
        "authority_class": "CONSTRUCT",
        "requirement_id": "req-1",
        "observation_digest": "sha256:abc",
        "capability": "write-greeting",
    }


class AutoFDERequirementAdmissionTests(unittest.TestCase):
    def test_deterministic_powl_and_admission(self):
        first_admission, first_powl = admit.admit(requirement(), "lab@abc", "urn:test")
        second_admission, second_powl = admit.admit(
            requirement(), "lab@abc", "urn:test"
        )
        self.assertEqual((first_admission, first_powl), (second_admission, second_powl))
        self.assertEqual(first_admission["standing"], "ALIVE")
        self.assertFalse(first_admission["do_authority"])
        self.assertEqual(first_powl.count("powl2:precedes"), 4)
        self.assertIn('powl2:activityLabel "resume-blocked-occurrence"', first_powl)

    def test_refuses_authority_escalation(self):
        value = requirement()
        value["authority_class"] = "DO"
        with self.assertRaisesRegex(ValueError, "AUTHORITY_ESCALATION"):
            admit.admit(value, "lab@abc", "urn:test")


if __name__ == "__main__":
    unittest.main()
