import os
import json
import config
import requests
import platform
from urllib3 import encode_multipart_formdata
from datetime import datetime, timezone
import helper

SESSION_FILE = "sessionid.json"

class tradingview:

    def __init__(self):
        print('Getting sessionid from file')
        self.sessionid = None

        # Try to load saved sessionid
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    self.sessionid = data.get("sessionid")
                print('Loaded sessionid from file')
            except Exception as e:
                print('Failed to load session file:', e)
                self.sessionid = None

        # Validate existing sessionid
        if self.sessionid:
            headers = {'cookie': 'sessionid=' + self.sessionid}
            try:
                test = requests.get(config.urls["tvcoins"], headers=headers, timeout=10)
                print("Session test status:", test.status_code)
                if test.status_code != 200:
                    print('Saved sessionid is invalid → will login again')
                    self.sessionid = None
            except Exception as e:
                print('Session validation failed:', e)
                self.sessionid = None

        # Login if no valid session
        if not self.sessionid:
            username = os.environ.get('username') or os.environ.get('tvusername')
            password = os.environ.get('password') or os.environ.get('tvpassword')

            if not username or not password:
                print("❌ Missing username or password in environment variables")
                self.sessionid = "invalid"
                return

            print('Logging in to TradingView...')
            payload = {'username': username, 'password': password, 'remember': 'on'}
            body, contentType = encode_multipart_formdata(payload)
            userAgent = f'TWAPI/3.0 ({platform.system()}; {platform.version()}; {platform.release()})'

            login_headers = {
                'origin': 'https://www.tradingview.com',
                'User-Agent': userAgent,
                'Content-Type': contentType,
                'referer': 'https://www.tradingview.com'
            }

            try:
                login = requests.post(config.urls["signin"], data=body, headers=login_headers, timeout=15)
                cookies = login.cookies.get_dict()

                if "sessionid" in cookies:
                    self.sessionid = cookies["sessionid"]
                    # Save to file
                    with open(SESSION_FILE, 'w') as f:
                        json.dump({"sessionid": self.sessionid}, f)
                    print("✅ Login successful. Sessionid saved.")
                else:
                    print("❌ Login failed. Check username/password.")
                    print("Response:", login.text[:200])
                    self.sessionid = "invalid"
            except Exception as e:
                print("❌ Exception during login:", e)
                self.sessionid = "invalid"

    def validate_username(self, username):
        users = requests.get(config.urls["username_hint"] + "?s=" + username)
        usersList = users.json()
        validUser = False
        verifiedUserName = ''
        for user in usersList:
            if user['username'].lower() == username.lower():
                validUser = True
                verifiedUserName = user['username']
        return {"validuser": validUser, "verifiedUserName": verifiedUserName}

    def get_access_details(self, username, pine_id):
        user_payload = {'pine_id': pine_id, 'username': username}

        user_headers = {
            'origin': 'https://www.tradingview.com',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': 'sessionid=' + self.sessionid
        }
        print("Getting access details for pine_id:", pine_id, "username:", username)

        usersResponse = requests.post(config.urls['list_users'] +
                                      '?limit=100&order_by=-created',
                                      headers=user_headers,
                                      data=user_payload)
        print("Raw response status:", usersResponse.status_code)
        print("Raw response body:", usersResponse.text[:500])  # Debug print

        try:
            userResponseJson = usersResponse.json()
        except:
            print("Failed to parse JSON")
            userResponseJson = []

        print("Parsed JSON:", userResponseJson)

        # Handle both old format {"results": [...]} and new format direct list
        if isinstance(userResponseJson, dict):
            users = userResponseJson.get('results', [])
        elif isinstance(userResponseJson, list):
            users = userResponseJson
        else:
            users = []

        access_details = {'pine_id': pine_id, 'username': username}
        hasAccess = False
        noExpiration = False
        expiration = str(datetime.now(timezone.utc))

        for user in users:
            if isinstance(user, dict) and user.get('username', '').lower() == username.lower():
                hasAccess = True
                strExpiration = user.get("expiration")
                if strExpiration is not None:
                    expiration = strExpiration
                else:
                    noExpiration = True
                break  # Stop after finding the user

        access_details['hasAccess'] = hasAccess
        access_details['noExpiration'] = noExpiration
        access_details['currentExpiration'] = expiration
        return access_details

    def add_access(self, access_details, extension_type, extension_length):
        noExpiration = access_details['noExpiration']
        access_details['expiration'] = access_details['currentExpiration']
        access_details['status'] = 'Not Applied'
        if not noExpiration:
            payload = {
                'pine_id': access_details['pine_id'],
                'username_recip': access_details['username']
            }
            if extension_type != 'L':
                expiration = helper.get_access_extension(
                    access_details['currentExpiration'], extension_type,
                    extension_length)
                payload['expiration'] = expiration
                access_details['expiration'] = expiration
            else:
                access_details['noExpiration'] = True
            enpoint_type = 'modify_access' if access_details[
                'hasAccess'] else 'add_access'

            body, contentType = encode_multipart_formdata(payload)

            headers = {
                'origin': 'https://www.tradingview.com',
                'Content-Type': contentType,
                'cookie': 'sessionid=' + self.sessionid
            }
            add_access_response = requests.post(config.urls[enpoint_type],
                                                data=body,
                                                headers=headers)
            access_details['status'] = 'Success' if (
                add_access_response.status_code == 200
                or add_access_response.status_code == 201) else 'Failure'
        return access_details

    def remove_access(self, access_details):
        payload = {
            'pine_id': access_details['pine_id'],
            'username_recip': access_details['username']
        }
        body, contentType = encode_multipart_formdata(payload)

        headers = {
            'origin': 'https://www.tradingview.com',
            'Content-Type': contentType,
            'cookie': 'sessionid=' + self.sessionid
        }
        remove_access_response = requests.post(config.urls['remove_access'],
                                               data=body,
                                               headers=headers)
        access_details['status'] = 'Success' if (remove_access_response.status_code
                                                 == 200) else 'Failure'
