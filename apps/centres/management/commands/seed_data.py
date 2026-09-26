import os
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.centres.models import DiagnosticCentre, DiagnosticTest
from apps.centres.services import upsert_offering

TESTS = [
    ("CBC", "Complete Blood Count", "Blood", "Haemoglobin, RBC, WBC and platelet counts."),
    ("LFT", "Liver Function Test", "Blood", "Bilirubin, SGOT, SGPT, ALP, proteins."),
    ("KFT", "Kidney Function Test", "Blood", "Urea, creatinine, uric acid, electrolytes."),
    ("LIPID", "Lipid Profile", "Blood", "Total cholesterol, HDL, LDL, triglycerides."),
    ("TSH", "Thyroid Stimulating Hormone", "Blood", "Screens thyroid function."),
    ("HBA1C", "HbA1c (Glycated Haemoglobin)", "Blood", "Average blood sugar over 3 months."),
    ("VITD", "Vitamin D (25-OH)", "Blood", "Vitamin D level."),
    ("XRAY-CHEST", "Chest X-Ray (PA View)", "Imaging", "Radiograph of the chest."),
]

# (name, address, city, pincode, {test_code: price in INR})
CENTRES = [
    (
        "HealthFirst Diagnostics", "12 Connaught Place", "Delhi", "110001",
        {"CBC": "350", "LFT": "750", "KFT": "700", "LIPID": "600", "TSH": "450",
         "HBA1C": "550", "VITD": "1400", "XRAY-CHEST": "500"},
    ),
    (
        "CarePlus Labs", "45 Lajpat Nagar II", "Delhi", "110024",
        {"CBC": "299", "LFT": "690", "LIPID": "549", "TSH": "399", "VITD": "1199"},
    ),
    (
        "Metro Diagnostics", "88 Linking Road, Bandra West", "Mumbai", "400050",
        {"CBC": "400", "KFT": "850", "LIPID": "700", "HBA1C": "650", "VITD": "1600",
         "XRAY-CHEST": "650"},
    ),
    (
        "Apex Pathology", "21 100 Feet Road, Indiranagar", "Bengaluru", "560038",
        {"CBC": "320", "LFT": "720", "KFT": "680", "TSH": "420", "HBA1C": "499",
         "XRAY-CHEST": "550"},
    ),
]


class Command(BaseCommand):
    help = "Seed an admin user, the test catalog, centres and prices. Safe to run repeatedly."

    @transaction.atomic
    def handle(self, *args, **options):
        admin_created = self._seed_admin()
        tests, tests_created = self._seed_tests()
        centres_created, offerings_created, offerings_updated = self._seed_centres(tests)

        self.stdout.write(self.style.SUCCESS("Seed complete:"))
        self.stdout.write(f"  admin user : {'created' if admin_created else 'already existed'}")
        self.stdout.write(f"  tests      : {tests_created} created, "
                          f"{len(TESTS) - tests_created} already existed")
        self.stdout.write(f"  centres    : {centres_created} created, "
                          f"{len(CENTRES) - centres_created} already existed")
        self.stdout.write(f"  offerings  : {offerings_created} created, "
                          f"{offerings_updated} already existed (price synced)")

    def _seed_admin(self) -> bool:
        User = get_user_model()
        email = os.environ.get("SEED_ADMIN_EMAIL", "admin@eve.local").strip().lower()
        if User.objects.filter(email=email).exists():
            return False  # never overwrite an existing admin's password
        User.objects.create_superuser(
            email=email,
            password=os.environ.get("SEED_ADMIN_PASSWORD", "Admin@12345"),
            full_name="EVE Admin",
        )
        return True

    def _seed_tests(self) -> tuple[dict[str, DiagnosticTest], int]:
        tests, created_count = {}, 0
        for code, name, sample_type, description in TESTS:
            test, created = DiagnosticTest.objects.get_or_create(
                code=code,
                defaults={"name": name, "sample_type": sample_type, "description": description},
            )
            tests[code] = test
            created_count += created
        return tests, created_count

    def _seed_centres(self, tests: dict[str, DiagnosticTest]) -> tuple[int, int, int]:
        centres_created = offerings_created = offerings_updated = 0
        for name, address, city, pincode, prices in CENTRES:
            centre, created = DiagnosticCentre.objects.get_or_create(
                name=name, city=city, defaults={"address": address, "pincode": pincode}
            )
            centres_created += created
            for code, price in prices.items():
                _, created = upsert_offering(centre=centre, test=tests[code], price=Decimal(price))
                if created:
                    offerings_created += 1
                else:
                    offerings_updated += 1
        return centres_created, offerings_created, offerings_updated
