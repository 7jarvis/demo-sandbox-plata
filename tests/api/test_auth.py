import allure
import pytest

from framework import builders
from framework.assertions import rejected
from framework.reporting import case
from framework.services import AuthService

pytestmark = [allure.feature("Registration and sign-in"), allure.story("Sign-in with a one-time code")]

WRONG_CODE = "000000"


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A registered customer signs in with the one-time code")
@case("TC-AUTH-01")
def test_sign_in_with_valid_code(auth: AuthService) -> None:
    customer = auth.register(builders.registration())

    challenge = auth.request_otp(customer.phone)
    token = auth.exchange(challenge.otp_id, auth.otp_code)

    assert token.token_type == "Bearer"
    assert token.expires_in > 0
    assert auth.me(token.access_token).id == customer.id


@allure.title("A wrong code is rejected and the number of attempts left is reported")
@case("TC-AUTH-02")
def test_wrong_code_reports_attempts_left(auth: AuthService) -> None:
    customer = auth.register(builders.registration())
    challenge = auth.request_otp(customer.phone)

    with rejected(401, "OTP_INVALID", field="code") as rejection:
        auth.exchange(challenge.otp_id, WRONG_CODE)

    assert rejection.error is not None
    assert rejection.error.fields["code"] == "2 attempts left"


@allure.title("After three wrong attempts even the right code is refused")
@case("TC-AUTH-03")
def test_code_is_locked_after_three_wrong_attempts(auth: AuthService) -> None:
    customer = auth.register(builders.registration())
    challenge = auth.request_otp(customer.phone)
    for _ in range(3):
        with rejected(401, "OTP_INVALID"):
            auth.exchange(challenge.otp_id, WRONG_CODE)

    with rejected(429, "OTP_ATTEMPTS_EXCEEDED"):
        auth.exchange(challenge.otp_id, auth.otp_code)

    # a new code works again
    assert auth.login(customer.phone).access_token


@allure.title("A code can be used only once")
@case("TC-AUTH-04")
def test_code_cannot_be_used_twice(auth: AuthService) -> None:
    customer = auth.register(builders.registration())
    challenge = auth.request_otp(customer.phone)
    auth.exchange(challenge.otp_id, auth.otp_code)

    with rejected(401, "OTP_INVALID"):
        auth.exchange(challenge.otp_id, auth.otp_code)


@allure.title("The code request does not reveal whether a phone is registered")
@case("TC-AUTH-05")
def test_unregistered_phone_gets_a_challenge_that_never_signs_in(auth: AuthService) -> None:
    challenge = auth.request_otp(builders.unique_phone())

    with rejected(401, "OTP_INVALID"):
        auth.exchange(challenge.otp_id, auth.otp_code)


@allure.title("Malformed code is a validation error: '{code}'")
@case("TC-AUTH-06")
@pytest.mark.parametrize("code", ["12345", "1234567", "12a456", ""])
def test_malformed_code_is_rejected(auth: AuthService, code: str) -> None:
    customer = auth.register(builders.registration())
    challenge = auth.request_otp(customer.phone)

    with rejected(422, "VALIDATION_ERROR", field="code"):
        auth.exchange_raw({"otp_id": challenge.otp_id, "code": code})

    # a malformed code does not burn an attempt
    assert auth.exchange(challenge.otp_id, auth.otp_code).access_token
