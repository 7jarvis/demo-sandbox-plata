import allure
import pytest

from framework import builders
from framework.assertions import rejected
from framework.reporting import case
from framework.services import AuthService

pytestmark = allure.feature("Registration and sign-in")


@allure.story("Registration")
class TestRegistration:
    @pytest.mark.smoke
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.title("A new customer registers and the profile is stored normalized")
    @case("TC-REG-01")
    def test_register_customer_returns_normalized_profile(self, auth: AuthService) -> None:
        phone = builders.unique_phone()
        email = builders.unique_email()

        customer = auth.register({"full_name": "  Ana   María López ", "phone": phone, "email": email.upper()})

        assert customer.full_name == "Ana María López"
        assert customer.phone == phone
        assert customer.email == email
        token = auth.login(phone).access_token
        assert auth.me(token) == customer

    @allure.title("A phone number can be registered only once")
    @case("TC-REG-02")
    def test_register_with_taken_phone_is_rejected(self, auth: AuthService) -> None:
        first = auth.register(builders.registration())

        with rejected(409, "PHONE_ALREADY_REGISTERED"):
            auth.register(builders.registration(phone=first.phone))

    @allure.title("An email can be registered only once, regardless of letter case")
    @case("TC-REG-03")
    def test_register_with_taken_email_in_other_case_is_rejected(self, auth: AuthService) -> None:
        first = auth.register(builders.registration())

        with rejected(409, "EMAIL_ALREADY_REGISTERED"):
            auth.register(builders.registration(email=first.email.upper()))

    @allure.title("Invalid {field} is rejected: '{value}'")
    @case("TC-REG-04")
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("phone", "+5255123456"),  # 9 digits
            ("phone", "+52551234567890"),  # 12 digits
            ("phone", "5512345678"),  # no country code
            ("phone", "+15512345678"),  # another country
            ("phone", "+52 5512345678"),  # space
            ("email", "plainaddress"),
            ("email", "ana@localhost"),
            ("email", "ana@@example.com"),
            ("full_name", "A"),
            ("full_name", "J0hn Smith"),
            ("full_name", "   "),
            ("full_name", "A" * 101),
        ],
    )
    def test_register_with_invalid_field_is_rejected(self, auth: AuthService, field: str, value: str) -> None:
        with rejected(422, "VALIDATION_ERROR", field=field):
            auth.register(builders.registration_dict(**{field: value}))

    @allure.title("Name length boundaries are accepted: {length} characters")
    @case("TC-REG-05")
    @pytest.mark.parametrize("length", [2, 100])
    def test_register_with_name_on_length_boundary(self, auth: AuthService, length: int) -> None:
        name = "Lu" + "z" * (length - 2)

        customer = auth.register(builders.registration(full_name=name))

        assert customer.full_name == name

    @allure.title("Every missing field is reported at once")
    @case("TC-REG-06")
    def test_register_with_empty_body_lists_all_missing_fields(self, auth: AuthService) -> None:
        with rejected(422, "VALIDATION_ERROR") as rejection:
            auth.register({})

        assert rejection.error is not None
        assert set(rejection.error.fields) == {"full_name", "phone", "email"}
