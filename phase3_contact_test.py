import json
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from app.db.session import SessionLocal
from app.models.contact import Contact
from app.models.user import User


BASE_URL = "http://localhost:8000"

USER_A_EMAIL = "phase3.contact.usera.20260930@example.com"
USER_B_EMAIL = "phase3.contact.userb.20260930@example.com"
PASSWORD = "Phase3Contact@12345"

CONTACT_A_EMAIL = "phase3.contact.primary.20260930@example.com"
CONTACT_B_EMAIL = "phase3.contact.secondary.20260930@example.com"

CSV_EMAIL_1 = "phase3.csv.one.20260930@example.com"
CSV_EMAIL_2 = "phase3.csv.two.20260930@example.com"


def request(
    method,
    path,
    data=None,
    headers=None
):
    url = BASE_URL + path

    request_obj = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method
    )

    try:
        with urllib.request.urlopen(
            request_obj,
            timeout=15
        ) as response:
            response_body = response.read().decode()

            if not response_body:
                return response.status, {}

            try:
                payload = json.loads(response_body)
            except json.JSONDecodeError:
                payload = response_body

            return response.status, payload

    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode()

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError:
            payload = response_body

        return exc.code, payload


def json_request(
    method,
    path,
    payload,
    token
):
    return request(
        method,
        path,
        json.dumps(payload).encode(),
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token
        }
    )


def login(email):
    body = urllib.parse.urlencode({
        "username": email,
        "password": PASSWORD
    }).encode()

    status, response = request(
        "POST",
        "/auth/login",
        body,
        {
            "Content-Type": (
                "application/x-www-form-urlencoded"
            )
        }
    )

    if status != 200:
        raise RuntimeError(
            f"Login failed for {email}: {status} {response}"
        )

    return response["access_token"]


def signup(email, name):
    cleanup_user_by_email(email)

    status, response = json_request_no_auth(
        "POST",
        "/auth/signup",
        {
            "name": name,
            "email": email,
            "password": PASSWORD
        }
    )

    if status != 200:
        raise RuntimeError(
            f"Signup failed for {email}: {status} {response}"
        )


def json_request_no_auth(
    method,
    path,
    payload
):
    return request(
        method,
        path,
        json.dumps(payload).encode(),
        {
            "Content-Type": "application/json"
        }
    )


def create_contact(
    token,
    name,
    email,
    company,
    status="new"
):
    return json_request(
        "POST",
        "/contacts",
        {
            "name": name,
            "email": email,
            "company": company,
            "linkedin_url": (
                "https://linkedin.com/in/"
                + uuid4().hex[:10]
            ),
            "status": status
        },
        token
    )


def upload_csv(
    token,
    filename,
    csv_content
):
    boundary = "----Phase3Boundary" + uuid4().hex

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; '
        f'name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n"
        f"\r\n"
        f"{csv_content}\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    return request(
        "POST",
        "/contacts/upload",
        body,
        {
            "Content-Type": (
                "multipart/form-data; boundary="
                + boundary
            ),
            "Authorization": "Bearer " + token
        }
    )


def cleanup_user_by_email(email):
    db = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(
                User.email == email
            )
            .first()
        )

        if not user:
            return

        db.query(Contact).filter(
            Contact.user_id == user.id
        ).delete(
            synchronize_session=False
        )

        db.delete(user)
        db.commit()

    finally:
        db.close()


def cleanup_test_users():
    cleanup_user_by_email(USER_A_EMAIL)
    cleanup_user_by_email(USER_B_EMAIL)


def main():
    cleanup_test_users()

    print("=== CONTACT REGRESSION START ===")

    signup(
        USER_A_EMAIL,
        "Phase 3 Contact User A"
    )

    signup(
        USER_B_EMAIL,
        "Phase 3 Contact User B"
    )

    token_a = login(USER_A_EMAIL)
    token_b = login(USER_B_EMAIL)

    print("TEMP USERS CREATED = 2")
    print("TOKENS RECEIVED = True")

    status, response = create_contact(
        token_a,
        "Phase 3 Primary Contact",
        CONTACT_A_EMAIL,
        "Phase 3 Company",
        "new"
    )

    print("CREATE STATUS =", status)
    print("CREATE RESPONSE =", response)

    if status != 201:
        raise SystemExit("CREATE CONTACT TEST FAILED")

    contact_a_id = response["id"]

    status, response = request(
        "GET",
        f"/contacts/{contact_a_id}",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("GET SINGLE STATUS =", status)

    if (
        status != 200
        or response.get("id") != contact_a_id
        or response.get("email") != CONTACT_A_EMAIL
    ):
        raise SystemExit("GET SINGLE CONTACT TEST FAILED")

    status, response = request(
        "GET",
        "/contacts",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("LIST STATUS =", status)
    print("LIST RESPONSE =", response)

    if (
        status != 200
        or response.get("total") != 1
        or response.get("pages") != 1
        or len(response.get("items", [])) != 1
    ):
        raise SystemExit("LIST CONTACT TEST FAILED")

    status, response = request(
        "GET",
        "/contacts?search=Primary",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("SEARCH STATUS =", status)

    if status != 200 or response.get("total") != 1:
        raise SystemExit("SEARCH TEST FAILED")

    status, response = request(
        "GET",
        "/contacts?company=Phase%203%20Company",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("COMPANY FILTER STATUS =", status)

    if status != 200 or response.get("total") != 1:
        raise SystemExit("COMPANY FILTER TEST FAILED")

    status, response = request(
        "GET",
        "/contacts?email=primary.20260930",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("EMAIL FILTER STATUS =", status)

    if status != 200 or response.get("total") != 1:
        raise SystemExit("EMAIL FILTER TEST FAILED")

    status, response = request(
        "GET",
        "/contacts?status=new",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("STATUS FILTER STATUS =", status)

    if status != 200 or response.get("total") != 1:
        raise SystemExit("STATUS FILTER TEST FAILED")

    status, response = request(
        "GET",
        "/contacts?status=invalid",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("INVALID STATUS FILTER =", status)

    if status != 422:
        raise SystemExit(
            "INVALID STATUS FILTER TEST FAILED"
        )

    status, response = create_contact(
        token_a,
        "Duplicate Contact",
        CONTACT_A_EMAIL,
        "Duplicate Company"
    )

    print("DUPLICATE CREATE STATUS =", status)

    if status != 409:
        raise SystemExit(
            "DUPLICATE CREATE TEST FAILED"
        )

    status, response = create_contact(
        token_a,
        "Phase 3 Secondary Contact",
        CONTACT_B_EMAIL,
        "Second Company",
        "new"
    )

    print("SECOND CREATE STATUS =", status)

    if status != 201:
        raise SystemExit(
            "SECOND CONTACT CREATE FAILED"
        )

    contact_b_id = response["id"]

    status, response = json_request(
        "PATCH",
        f"/contacts/{contact_a_id}",
        {
            "name": "Phase 3 Primary Contact Updated",
            "company": "Updated Phase 3 Company",
            "linkedin_url": (
                "https://linkedin.com/in/updated-phase3"
            ),
            "status": "contacted"
        },
        token_a
    )

    print("UPDATE STATUS =", status)
    print("UPDATE RESPONSE =", response)

    if (
        status != 200
        or response.get("name")
        != "Phase 3 Primary Contact Updated"
        or response.get("company")
        != "Updated Phase 3 Company"
        or response.get("status") != "contacted"
    ):
        raise SystemExit("UPDATE CONTACT TEST FAILED")

    status, response = json_request(
        "PATCH",
        f"/contacts/{contact_a_id}",
        {
            "email": CONTACT_B_EMAIL
        },
        token_a
    )

    print("DUPLICATE UPDATE STATUS =", status)

    if status != 409:
        raise SystemExit(
            "DUPLICATE UPDATE TEST FAILED"
        )

    status, response = json_request(
        "PATCH",
        f"/contacts/{contact_a_id}",
        {
            "status": "invalid"
        },
        token_a
    )

    print("INVALID STATUS UPDATE =", status)

    if status != 422:
        raise SystemExit(
            "INVALID STATUS UPDATE TEST FAILED"
        )

    status, response = request(
        "GET",
        f"/contacts/{contact_a_id}",
        headers={
            "Authorization": "Bearer " + token_b
        }
    )

    print("CROSS USER GET STATUS =", status)

    if status != 404:
        raise SystemExit(
            "CROSS USER GET TEST FAILED"
        )

    status, response = json_request(
        "PATCH",
        f"/contacts/{contact_a_id}",
        {
            "name": "Unauthorized Update"
        },
        token_b
    )

    print("CROSS USER UPDATE STATUS =", status)

    if status != 404:
        raise SystemExit(
            "CROSS USER UPDATE TEST FAILED"
        )

    status, response = request(
        "DELETE",
        f"/contacts/{contact_a_id}",
        headers={
            "Authorization": "Bearer " + token_b
        }
    )

    print("CROSS USER DELETE STATUS =", status)

    if status != 404:
        raise SystemExit(
            "CROSS USER DELETE TEST FAILED"
        )

    status, response = request(
        "GET",
        "/contacts",
        headers={
            "Authorization": "Bearer " + token_b
        }
    )

    print("CROSS USER LIST TOTAL =", response.get("total"))

    if status != 200 or response.get("total") != 0:
        raise SystemExit(
            "CROSS USER LIST TEST FAILED"
        )

    csv_content = (
        "name,email,company,linkedin_url\n"
        "CSV Regression One,"
        f"{CSV_EMAIL_1},CSV Company One,"
        "https://linkedin.com/in/csv-one\n"
        "CSV Regression Two,"
        f"{CSV_EMAIL_2},CSV Company Two,"
        "https://linkedin.com/in/csv-two\n"
    )

    status, response = upload_csv(
        token_a,
        "phase3_contacts.csv",
        csv_content
    )

    print("CSV UPLOAD STATUS =", status)
    print("CSV UPLOAD RESPONSE =", response)

    if (
        status != 200
        or response.get("added") != 2
        or response.get("duplicates") != 0
    ):
        raise SystemExit("CSV UPLOAD TEST FAILED")

    status, response = upload_csv(
        token_a,
        "phase3_contacts.csv",
        csv_content
    )

    print("CSV DUPLICATE UPLOAD STATUS =", status)
    print(
        "CSV DUPLICATE UPLOAD RESPONSE =",
        response
    )

    if (
        status != 200
        or response.get("added") != 0
        or response.get("duplicates") != 2
    ):
        raise SystemExit(
            "CSV DUPLICATE UPLOAD TEST FAILED"
        )

    status, response = request(
        "GET",
        "/contacts?status=new",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("FINAL NEW CONTACT TOTAL =", response.get("total"))

    if status != 200 or response.get("total") != 3:
        raise SystemExit(
            "FINAL CONTACT COUNT TEST FAILED"
        )

    created_contact_ids = [
        contact_a_id,
        contact_b_id
    ]

    csv_status, csv_response = request(
        "GET",
        "/contacts?search=CSV%20Regression",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    if csv_status != 200:
        raise SystemExit(
            "CSV CONTACT SEARCH FAILED"
        )

    for contact in csv_response.get(
        "items",
        []
    ):
        created_contact_ids.append(
            contact["id"]
        )

    status, response = request(
        "DELETE",
        f"/contacts/{contact_b_id}",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("DELETE STATUS =", status)

    if status != 204:
        raise SystemExit(
            "DELETE CONTACT TEST FAILED"
        )

    if contact_b_id in created_contact_ids:
        created_contact_ids.remove(contact_b_id)

    for contact_id in created_contact_ids:
        status, response = request(
            "DELETE",
            f"/contacts/{contact_id}",
            headers={
                "Authorization": "Bearer " + token_a
            }
        )

        if status != 204:
            raise SystemExit(
                f"CLEANUP DELETE FAILED FOR {contact_id}"
            )

    status, response = request(
        "GET",
        "/contacts",
        headers={
            "Authorization": "Bearer " + token_a
        }
    )

    print("POST CLEANUP CONTACT TOTAL =", response.get("total"))

    if status != 200 or response.get("total") != 0:
        raise SystemExit(
            "CONTACT CLEANUP VERIFICATION FAILED"
        )

    print("CONTACT REGRESSION PASSED")

    cleanup_test_users()

    print("USER CLEANUP COMPLETE")


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_test_users()