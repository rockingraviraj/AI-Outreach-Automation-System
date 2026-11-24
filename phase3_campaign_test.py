import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode


BASE_URL = "http://127.0.0.1:8000"


def request(method, path, token=None, data=None):
    url = BASE_URL + path

    headers = {
        "Content-Type": "application/json"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()

            if not raw:
                return response.status, None

            return response.status, json.loads(raw.decode("utf-8"))

    except urllib.error.HTTPError as error:
        raw = error.read()

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8")

        return error.code, payload


def signup(name, email, password):
    return request(
        "POST",
        "/auth/signup",
        data={
            "name": name,
            "email": email,
            "password": password
        }
    )


def login(email, password):
    url = BASE_URL + "/auth/login"

    form_data = urlencode({
        "username": email,
        "password": password
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=form_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()

            if not raw:
                return response.status, None

            return response.status, json.loads(raw.decode("utf-8"))

    except urllib.error.HTTPError as error:
        raw = error.read()

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8")

        return error.code, payload


def assert_status(actual, expected, label):
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected}, got {actual}"
        )


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    print("=== CAMPAIGN REGRESSION START ===")

    timestamp = str(int(time.time()))

    user1_email = f"phase3.campaign.user1.{timestamp}@example.com"
    user2_email = f"phase3.campaign.user2.{timestamp}@example.com"

    password = "Phase3CampaignPass123!"

    user1_id = None
    user2_id = None

    token1 = None
    token2 = None

    campaign1_id = None
    campaign2_id = None

    contact1_id = None
    contact2_id = None
    user2_contact_id = None

    try:
        # =========================================================
        # CREATE USERS
        # =========================================================

        status, response = signup(
            "Phase 3 Campaign User 1",
            user1_email,
            password
        )

        assert_status(
            status,
            200,
            "USER 1 SIGNUP"
        )

        status, response = signup(
            "Phase 3 Campaign User 2",
            user2_email,
            password
        )

        assert_status(
            status,
            200,
            "USER 2 SIGNUP"
        )

        print("TEMP USERS CREATED = 2")

        # =========================================================
        # LOGIN
        # =========================================================

        status, login1 = login(
            user1_email,
            password
        )

        assert_status(
            status,
            200,
            "USER 1 LOGIN"
        )

        status, login2 = login(
            user2_email,
            password
        )

        assert_status(
            status,
            200,
            "USER 2 LOGIN"
        )

        token1 = login1["access_token"]
        token2 = login2["access_token"]

        print("TOKENS RECEIVED =", bool(token1 and token2))

        # =========================================================
        # GET USER PROFILES
        # =========================================================

        status, profile1 = request(
            "GET",
            "/user/profile",
            token=token1
        )

        assert_status(
            status,
            200,
            "USER 1 PROFILE"
        )

        status, profile2 = request(
            "GET",
            "/user/profile",
            token=token2
        )

        assert_status(
            status,
            200,
            "USER 2 PROFILE"
        )

        user1_id = profile1["id"]
        user2_id = profile2["id"]

        print("USER IDS =", user1_id, user2_id)

        # =========================================================
        # CREATE CONTACTS FOR USER 1
        # =========================================================

        status, contact1 = request(
            "POST",
            "/contacts",
            token=token1,
            data={
                "name": "Campaign Contact One",
                "email": f"phase3.campaign.contact1.{timestamp}@example.com",
                "company": "Campaign Company One"
            }
        )

        assert_status(
            status,
            201,
            "CONTACT 1 CREATE"
        )

        contact1_id = contact1["id"]

        status, contact2 = request(
            "POST",
            "/contacts",
            token=token1,
            data={
                "name": "Campaign Contact Two",
                "email": f"phase3.campaign.contact2.{timestamp}@example.com",
                "company": "Campaign Company Two"
            }
        )

        assert_status(
            status,
            201,
            "CONTACT 2 CREATE"
        )

        contact2_id = contact2["id"]

        print("CONTACTS CREATED =", contact1_id, contact2_id)

        # =========================================================
        # CREATE CAMPAIGN
        # =========================================================

        status, campaign = request(
            "POST",
            "/campaign",
            token=token1,
            data={
                "name": "Phase 3 Campaign"
            }
        )

        assert_status(
            status,
            201,
            "CAMPAIGN CREATE"
        )

        campaign1_id = campaign["id"]

        assert_true(
            campaign["status"] == "draft",
            "New campaign should start in draft status"
        )

        assert_true(
            campaign["user_id"] == user1_id,
            "Campaign should belong to user 1"
        )

        print("CREATE STATUS =", status)
        print("CREATE RESPONSE =", campaign)

        # =========================================================
        # GET SINGLE CAMPAIGN
        # =========================================================

        status, response = request(
            "GET",
            f"/campaign/{campaign1_id}",
            token=token1
        )

        assert_status(
            status,
            200,
            "GET SINGLE CAMPAIGN"
        )

        print("GET SINGLE STATUS =", status)

        # =========================================================
        # LIST CAMPAIGNS
        # =========================================================

        status, response = request(
            "GET",
            "/campaign",
            token=token1
        )

        assert_status(
            status,
            200,
            "CAMPAIGN LIST"
        )

        assert_true(
            response["total"] == 1,
            "User 1 should have exactly one campaign"
        )

        print("LIST STATUS =", status)
        print("LIST RESPONSE =", response)

        # =========================================================
        # PAGINATION
        # =========================================================

        status, response = request(
            "GET",
            "/campaign?page=1&limit=1",
            token=token1
        )

        assert_status(
            status,
            200,
            "CAMPAIGN PAGINATION"
        )

        assert_true(
            response["page"] == 1,
            "Pagination page should be 1"
        )

        assert_true(
            response["limit"] == 1,
            "Pagination limit should be 1"
        )

        print("PAGINATION STATUS =", status)

        # =========================================================
        # CAMPAIGN NAME UPDATE
        # =========================================================

        status, updated_campaign = request(
            "PATCH",
            f"/campaign/{campaign1_id}",
            token=token1,
            data={
                "name": "Phase 3 Campaign Updated"
            }
        )

        assert_status(
            status,
            200,
            "CAMPAIGN UPDATE"
        )

        assert_true(
            updated_campaign["name"] == "Phase 3 Campaign Updated",
            "Campaign name should be updated"
        )

        print("UPDATE STATUS =", status)
        print("UPDATE RESPONSE =", updated_campaign)

        # =========================================================
        # EMPTY NAME VALIDATION
        # =========================================================

        status, response = request(
            "PATCH",
            f"/campaign/{campaign1_id}",
            token=token1,
            data={
                "name": "   "
            }
        )

        assert_status(
            status,
            422,
            "EMPTY CAMPAIGN NAME"
        )

        print("EMPTY NAME UPDATE =", status)

        # =========================================================
        # TOO LONG NAME VALIDATION
        # =========================================================

        status, response = request(
            "PATCH",
            f"/campaign/{campaign1_id}",
            token=token1,
            data={
                "name": "A" * 101
            }
        )

        assert_status(
            status,
            422,
            "CAMPAIGN NAME > 100"
        )

        print("LONG NAME UPDATE =", status)

        # =========================================================
        # STATUS CANNOT BE CHANGED THROUGH PATCH
        # =========================================================

        status, response = request(
            "PATCH",
            f"/campaign/{campaign1_id}",
            token=token1,
            data={
                "status": "completed"
            }
        )

        assert_status(
            status,
            409,
            "CAMPAIGN STATUS UPDATE"
        )

        print("STATUS PATCH BLOCKED =", status)

        # =========================================================
        # ADD CONTACTS
        # =========================================================

        status, response = request(
            "POST",
            f"/campaign/{campaign1_id}/contacts",
            token=token1,
            data={
                "contact_ids": [
                    contact1_id,
                    contact2_id
                ]
            }
        )

        assert_status(
            status,
            200,
            "ADD CAMPAIGN CONTACTS"
        )

        assert_true(
            response["total"] == 2,
            "Campaign should contain two contacts"
        )

        print("ADD CONTACTS STATUS =", status)
        print("ADD CONTACTS RESPONSE =", response)

        # =========================================================
        # DUPLICATE ASSOCIATION
        # Sending duplicate IDs should still leave only 2 links.
        # =========================================================

        status, response = request(
            "POST",
            f"/campaign/{campaign1_id}/contacts",
            token=token1,
            data={
                "contact_ids": [
                    contact1_id,
                    contact1_id,
                    contact2_id
                ]
            }
        )

        assert_status(
            status,
            200,
            "DUPLICATE CAMPAIGN CONTACT ASSOCIATION"
        )

        assert_true(
            response["total"] == 2,
            "Duplicate association should not create extra links"
        )

        print("DUPLICATE ASSOCIATION STATUS =", status)
        print("DUPLICATE ASSOCIATION TOTAL =", response["total"])

        # =========================================================
        # GET CAMPAIGN CONTACTS
        # =========================================================

        status, response = request(
            "GET",
            f"/campaign/{campaign1_id}/contacts",
            token=token1
        )

        assert_status(
            status,
            200,
            "GET CAMPAIGN CONTACTS"
        )

        assert_true(
            response["total"] == 2,
            "Campaign contacts total should be 2"
        )

        print("GET CAMPAIGN CONTACTS STATUS =", status)
        print("GET CAMPAIGN CONTACTS RESPONSE =", response)

        # =========================================================
        # REMOVE ONE CONTACT
        # =========================================================

        status, response = request(
            "DELETE",
            f"/campaign/{campaign1_id}/contacts/{contact2_id}",
            token=token1
        )

        assert_status(
            status,
            204,
            "REMOVE CAMPAIGN CONTACT"
        )

        print("REMOVE CONTACT STATUS =", status)

        # =========================================================
        # VERIFY REMOVAL
        # =========================================================

        status, response = request(
            "GET",
            f"/campaign/{campaign1_id}/contacts",
            token=token1
        )

        assert_status(
            status,
            200,
            "VERIFY CONTACT REMOVAL"
        )

        assert_true(
            response["total"] == 1,
            "Exactly one campaign contact should remain"
        )

        print("POST REMOVE CONTACT TOTAL =", response["total"])

        # =========================================================
        # REMOVE SAME CONTACT AGAIN
        # =========================================================

        status, response = request(
            "DELETE",
            f"/campaign/{campaign1_id}/contacts/{contact2_id}",
            token=token1
        )

        assert_status(
            status,
            404,
            "REMOVE NON ASSOCIATED CONTACT"
        )

        print("REMOVE AGAIN STATUS =", status)

        # =========================================================
        # INVALID CONTACT ID
        # =========================================================

        status, response = request(
            "POST",
            f"/campaign/{campaign1_id}/contacts",
            token=token1,
            data={
                "contact_ids": [
                    999999999
                ]
            }
        )

        assert_status(
            status,
            404,
            "INVALID CONTACT ID"
        )

        print("INVALID CONTACT STATUS =", status)

        # =========================================================
        # RE-ADD REMOVED CONTACT
        # =========================================================

        status, response = request(
            "POST",
            f"/campaign/{campaign1_id}/contacts",
            token=token1,
            data={
                "contact_ids": [
                    contact2_id
                ]
            }
        )

        assert_status(
            status,
            200,
            "RE-ADD CONTACT"
        )

        assert_true(
            response["total"] == 2,
            "Campaign should have two contacts again"
        )

        print("RE-ADD CONTACT STATUS =", status)

        # =========================================================
        # USER 2 SHOULD NOT SEE USER 1 CAMPAIGN
        # =========================================================

        status, response = request(
            "GET",
            f"/campaign/{campaign1_id}",
            token=token2
        )

        assert_status(
            status,
            404,
            "CROSS USER GET CAMPAIGN"
        )

        print("CROSS USER GET STATUS =", status)

        # =========================================================
        # USER 2 SHOULD NOT SEE CAMPAIGNS
        # =========================================================

        status, response = request(
            "GET",
            "/campaign",
            token=token2
        )

        assert_status(
            status,
            200,
            "CROSS USER CAMPAIGN LIST"
        )

        assert_true(
            response["total"] == 0,
            "User 2 should not see user 1 campaigns"
        )

        print("CROSS USER LIST TOTAL =", response["total"])

        # =========================================================
        # USER 2 SHOULD NOT MODIFY CAMPAIGN
        # =========================================================

        status, response = request(
            "PATCH",
            f"/campaign/{campaign1_id}",
            token=token2,
            data={
                "name": "Unauthorized Campaign Update"
            }
        )

        assert_status(
            status,
            404,
            "CROSS USER UPDATE CAMPAIGN"
        )

        print("CROSS USER UPDATE STATUS =", status)

        # =========================================================
        # USER 2 SHOULD NOT ADD OWN CONTACT TO USER 1 CAMPAIGN
        # =========================================================

        status, contact_user2 = request(
            "POST",
            "/contacts",
            token=token2,
            data={
                "name": "User Two Contact",
                "email": f"phase3.campaign.user2.contact.{timestamp}@example.com",
                "company": "User Two Company"
            }
        )

        assert_status(
            status,
            201,
            "USER 2 CONTACT CREATE"
        )

        user2_contact_id = contact_user2["id"]

        status, response = request(
            "POST",
            f"/campaign/{campaign1_id}/contacts",
            token=token2,
            data={
                "contact_ids": [
                    user2_contact_id
                ]
            }
        )

        assert_status(
            status,
            404,
            "CROSS USER ADD CONTACT"
        )

        print("CROSS USER ADD CONTACT STATUS =", status)

        # =========================================================
        # USER 2 SHOULD NOT REMOVE USER 1 CAMPAIGN CONTACT
        # =========================================================

        status, response = request(
            "DELETE",
            f"/campaign/{campaign1_id}/contacts/{contact1_id}",
            token=token2
        )

        assert_status(
            status,
            404,
            "CROSS USER REMOVE CONTACT"
        )

        print("CROSS USER REMOVE CONTACT STATUS =", status)

        # =========================================================
        # CREATE SECOND CAMPAIGN FOR LIST / DELETE TEST
        # =========================================================

        status, campaign2 = request(
            "POST",
            "/campaign",
            token=token1,
            data={
                "name": "Phase 3 Delete Campaign"
            }
        )

        assert_status(
            status,
            201,
            "SECOND CAMPAIGN CREATE"
        )

        campaign2_id = campaign2["id"]

        print("SECOND CAMPAIGN CREATE STATUS =", status)

        # =========================================================
        # LIST SHOULD NOW SHOW TWO CAMPAIGNS
        # =========================================================

        status, response = request(
            "GET",
            "/campaign",
            token=token1
        )

        assert_status(
            status,
            200,
            "FINAL CAMPAIGN LIST"
        )

        assert_true(
            response["total"] == 2,
            "User 1 should now have two campaigns"
        )

        print("FINAL CAMPAIGN TOTAL =", response["total"])

        # =========================================================
        # DELETE DRAFT CAMPAIGN
        # =========================================================

        status, response = request(
            "DELETE",
            f"/campaign/{campaign2_id}",
            token=token1
        )

        assert_status(
            status,
            204,
            "DELETE DRAFT CAMPAIGN"
        )

        print("DELETE DRAFT STATUS =", status)

        # =========================================================
        # VERIFY SECOND CAMPAIGN IS GONE
        # =========================================================

        status, response = request(
            "GET",
            f"/campaign/{campaign2_id}",
            token=token1
        )

        assert_status(
            status,
            404,
            "VERIFY DELETED CAMPAIGN"
        )

        print("VERIFY DELETED CAMPAIGN STATUS =", status)

        # =========================================================
        # DELETE NON-EXISTING CAMPAIGN
        # =========================================================

        status, response = request(
            "DELETE",
            "/campaign/999999999",
            token=token1
        )

        assert_status(
            status,
            404,
            "DELETE NON EXISTING CAMPAIGN"
        )

        print("DELETE NON EXISTING STATUS =", status)

        # =========================================================
        # FINAL SUCCESS
        # =========================================================

        print("CAMPAIGN REGRESSION PASSED")

    finally:
        print("CLEANUP STARTED")

        # Best-effort API cleanup first. Each request is isolated so one
        # cleanup failure does not prevent the remaining cleanup steps.
        cleanup_requests = []

        if campaign1_id is not None and token1:
            cleanup_requests.append((
                "DELETE",
                f"/campaign/{campaign1_id}",
                token1
            ))

        if campaign2_id is not None and token1:
            cleanup_requests.append((
                "DELETE",
                f"/campaign/{campaign2_id}",
                token1
            ))

        if contact1_id is not None and token1:
            cleanup_requests.append(("DELETE", f"/contacts/{contact1_id}", token1))

        if contact2_id is not None and token1:
            cleanup_requests.append(("DELETE", f"/contacts/{contact2_id}", token1))

        if user2_contact_id is not None and token2:
            cleanup_requests.append((
                "DELETE",
                f"/contacts/{user2_contact_id}",
                token2
            ))

        for method, path, token in cleanup_requests:
            try:
                cleanup_status, _ = request(method, path, token=token)
                print(f"API CLEANUP {method} {path} -> {cleanup_status}")
            except Exception as error:
                print(f"API CLEANUP FAILED for {path}: {error}")

        print("API CLEANUP REQUESTS COMPLETE")

        # Database fallback uses the exact, uniquely generated test emails.
        # Delete only test-owned dependent rows, then the two temporary users.
        # The generated email values contain only fixed text and timestamp digits;
        # SQL literals are still escaped before being inserted into the statement.
        try:
            import subprocess

            user1_email_sql = "'" + user1_email.replace("'", "''") + "'"
            user2_email_sql = "'" + user2_email.replace("'", "''") + "'"
            test_emails_sql = f"{user1_email_sql}, {user2_email_sql}"

            cleanup_sql = f"""
                DELETE FROM emails
                WHERE campaign_id IN (
                    SELECT id FROM campaigns
                    WHERE user_id IN (
                        SELECT id FROM users WHERE email IN ({test_emails_sql})
                    )
                )
                OR contact_id IN (
                    SELECT id FROM contacts
                    WHERE user_id IN (
                        SELECT id FROM users WHERE email IN ({test_emails_sql})
                    )
                );

                DELETE FROM campaign_contacts
                WHERE campaign_id IN (
                    SELECT id FROM campaigns
                    WHERE user_id IN (
                        SELECT id FROM users WHERE email IN ({test_emails_sql})
                    )
                )
                OR contact_id IN (
                    SELECT id FROM contacts
                    WHERE user_id IN (
                        SELECT id FROM users WHERE email IN ({test_emails_sql})
                    )
                );

                DELETE FROM campaigns
                WHERE user_id IN (
                    SELECT id FROM users WHERE email IN ({test_emails_sql})
                );

                DELETE FROM contacts
                WHERE user_id IN (
                    SELECT id FROM users WHERE email IN ({test_emails_sql})
                );

                DELETE FROM users
                WHERE email IN ({test_emails_sql});

                SELECT COUNT(*) AS leftover_temp_users
                FROM users
                WHERE email IN ({test_emails_sql});
            """

            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "ai_outreach_user",
                    "-d",
                    "ai_outreach",
                    "-c",
                    cleanup_sql
                ],
                capture_output=True,
                text=True,
                check=False
            )

            if result.stdout:
                print(result.stdout.strip())

            if result.returncode == 0:
                print("DATABASE CLEANUP COMMAND COMPLETED")
            else:
                print("DATABASE CLEANUP FAILED:")
                print(result.stderr.strip())

        except Exception as error:
            print("USER DB CLEANUP ERROR =", error)

        print("=== CAMPAIGN REGRESSION END ===")


if __name__ == "__main__":
    main()