from pc_jamf import PCJAMF
import configparser
import pytest
import datetime
from pprint import pprint
import os.path
import time

config = configparser.ConfigParser()
config.read("config.txt")
username = config["credentials"].get("username", None).replace("@pinecrest.edu", "")
password = config["credentials"].get("password", None)
server = config["parameters"].get("server_name", None)

TEST_DEVICE_ID = 779

def test_available():
    assert PCJAMF.available(server=server)


@pytest.fixture(scope="session")
def jamf_session():
    if PCJAMF.available(server=server):
        jamf = PCJAMF(username, password, server=server)
        yield jamf
    else:
        raise Exception(
            "PC JAMF Server not available. Check your connection and try again."
        )


@pytest.fixture(scope="session")
def js_authenticated(jamf_session):
    if not jamf_session.authenticated:
        jamf_session.authenticate()
    return jamf_session


def test_authenticated():
    jamf_session = PCJAMF(username, password, server)
    assert not jamf_session.authenticated
    jamf_session.authenticate()
    assert jamf_session.authenticated
    token, auth_exp_holding = jamf_session.token, jamf_session.auth_expiration
    jamf_session.auth_expiration = datetime.datetime.now() - datetime.timedelta(hours=1)
    assert not jamf_session.authenticated
    jamf_session.auth_expiration = auth_exp_holding
    jamf_session.token = None
    assert not jamf_session.authenticated
    auth_exp_holding = jamf_session.auth_expiration
    assert not jamf_session.authenticated
    jamf_session.token, jamf_session.auth_expiration = token, auth_exp_holding
    assert jamf_session.authenticated


def test_validate_token(js_authenticated):
    assert js_authenticated.validate()


def test_login(jamf_session):
    jamf_session.authenticate()
    assert jamf_session.authenticated


def test_all_devices(js_authenticated):
    devices = js_authenticated.all_devices()
    pprint(devices)
    assert len(devices) > 0


def test_search_devices_by_serial(js_authenticated):
    serial = "***REMOVED***"
    devices = js_authenticated.search_devices(serial=serial)
    assert len(devices) > 0
    with pytest.raises(Exception):
        serial = "invalid serial number"
        assert js_authenticated.get_devices_by_serial(serial)


def test_search_devices_by_uuid(js_authenticated):
    udid = "***REMOVED***"
    devices = js_authenticated.search_devices(udid=udid)
    assert len(devices) > 0
    with pytest.raises(Exception):
        udid = "null"
        assert js_authenticated.search_devices(udid=udid)


def test_get_device(js_authenticated):
    device = js_authenticated.device(device_id=TEST_DEVICE_ID)
    assert device["id"] == TEST_DEVICE_ID
    assert device.items()

def test_flush_mobile_device_commands(js_authenticated):
    assert js_authenticated.flush_mobile_device_commands(TEST_DEVICE_ID)

def test_update_device_name(js_authenticated):
    # Setup
    device_test_name = "fi-cart3-test"
    js_authenticated.flush_mobile_device_commands(device_id=TEST_DEVICE_ID)
    time.sleep(0.25)

    # Exercise
    updated_device = js_authenticated.update_device_name(
        device_id=TEST_DEVICE_ID, name=device_test_name
    )

    # Verify
    assert '<status>Command sent</status>' in updated_device

    # Cleanup
    js_authenticated.flush_mobile_device_commands(device_id=TEST_DEVICE_ID, status="Pending")


def test_clear_location_from_device(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID
    device = js_authenticated.device(device_id, detail=True)
    old_location = device.get('location')

    # Exercise
    js_authenticated.clear_location_from_device(device_id)

    # Verify
    device = js_authenticated.device(device_id, detail=True)
    assert not device['location']

    # Cleanup
    js_authenticated.update_device(device_id, location=old_location)

def test_add_device_to_prestage_by_device_id(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID
    serial_number = js_authenticated.device(device_id=device_id)['serialNumber']
    prestage_endpoint = js_authenticated._url('/uapi/v1/mobile-device-prestages/scope')
    before_prestage = js_authenticated.get_prestage_id_for_device(device_id)
    if before_prestage:
        js_authenticated.remove_device_from_prestage(device_id=device_id)
    test_prestage = 58
    
    # Exercise
    js_authenticated.add_device_to_prestage(device_id=device_id, prestage_id=test_prestage)

    # Verify
    prestages = js_authenticated.session.get(prestage_endpoint).json()['serialsByPrestageId']
    assert prestages[serial_number] == test_prestage

    # Cleanup
    js_authenticated.remove_device_from_prestage(device_id=device_id)
    if before_prestage:
        js_authenticated.add_device_to_prestage(device_id=device_id, prestage_id=before_prestage)

def test_add_device_to_prestage_by_serial(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID
    serial_number = js_authenticated.device(device_id=device_id)['serialNumber']
    prestage_endpoint = js_authenticated._url('/uapi/v1/mobile-device-prestages/scope')
    before_prestage = js_authenticated.session.get(prestage_endpoint).json()['serialsByPrestageId'].get(serial_number)
    if before_prestage:
        js_authenticated.remove_device_from_prestage(serial_number=serial_number)
    test_prestage = 58
    
    # Exercise
    js_authenticated.add_device_to_prestage(serial_number=serial_number, prestage_id=test_prestage)

    # Verify
    prestages = js_authenticated.session.get(prestage_endpoint).json()['serialsByPrestageId']
    assert prestages[serial_number] == test_prestage

    # Cleanup
    js_authenticated.remove_device_from_prestage(serial_number=serial_number)
    if before_prestage:
        js_authenticated.add_device_to_prestage(serial_number=serial_number, prestage_id=before_prestage)

def test_device_flattened(js_authenticated):
    device_id = TEST_DEVICE_ID
    time.sleep(0.25)
    device = js_authenticated.device(device_id=device_id, detail=True)
    device_room_name = device.get('location').get('room')
    device = js_authenticated.device_flattened(device_id=device_id)
    assert "lastInventoryUpdateTimestamp" in device
    assert device.get("location_room") == device_room_name

def test_os_update_device(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID

    # Exercise
    updated_device = js_authenticated.update_os(
        device_id=device_id, force_install=True)

    # Verify
    assert '<status>Command sent</status>' in updated_device

    # Cleanup
    js_authenticated.flush_mobile_device_commands(device_id)

def test_token_invalidation():
    # Setup - create a one-off jamf session
    test_session = PCJAMF(username, password, server)
    test_session.authenticate()

    # Exercise
    assert test_session.authenticated
    assert test_session.invalidate()

    # Verify
    with pytest.raises(AttributeError):
        assert test_session.token
        assert test_session.auth_expiration
    assert not test_session.validate()

    # Cleanup - none


def test_update_device(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID
    device = js_authenticated.device(device_id=device_id, detail=True)
    old_device_asset_tag = device["assetTag"]
    device_asset_tag_test = f"{old_device_asset_tag}-test"

    # Exercise
    assert js_authenticated.update_device(device_id, assetTag=device_asset_tag_test)
    device = js_authenticated.device(device_id, detail=True)

    # Verify
    assert device["assetTag"] == device_asset_tag_test

    # Cleanup
    js_authenticated.update_device(device_id, assetTag=old_device_asset_tag)

def test_get_buildings(js_authenticated):
    # Setup - none

    # Exercise
    buildings = js_authenticated.get_buildings()

    # Verify
    assert len(buildings) > 1

    # Cleanup - none

def test_get_building(js_authenticated):
    # Setup
    building_name = '***REMOVED***'
    desired_id = 4

    # Exercise
    building = js_authenticated.get_building(building_name)

    # Verify
    assert building['id'] == desired_id
    assert building['name'] == building_name

    # Cleanup - none

def test_get_empty_building(js_authenticated):
    # Setup
    building_name = None

    # Exercise
    building = js_authenticated.get_building(building_name)

    # Verify
    assert not building

    # Cleanup - none

def test_get_departments(js_authenticated):
    # Setup - none

    # Exercise
    departments = js_authenticated.get_departments()

    # Verify
    assert len(departments) > 1

    # Cleanup - none

def test_get_department(js_authenticated):
    # Setup
    department_name = '***REMOVED***'
    desired_id = 25

    # Exercise
    department = js_authenticated.get_department(department_name)

    # Verify
    assert department['id'] == desired_id
    assert department['name'] == department_name

def test_get_empty_department(js_authenticated):
    # Setup
    department_name = None

    # Exercise
    department = js_authenticated.get_department(department_name)

    # Verify
    assert not department

    # Cleanup - none

def test_strip_extra_location_information(js_authenticated):
    # Setup
    building_name = '***REMOVED***'
    desired_id = 4

    # Exercise
    building = js_authenticated.get_building(building_name)
    building_stripped = js_authenticated.strip_extra_location_information(building)

    # Verify
    assert building_stripped['id'] == desired_id
    assert building_stripped['name'] == building_name
    assert 'streetAddress1' not in building_stripped

    # Cleanup - none

def test_strip_empty_extra_location_information(js_authenticated):
    # Setup
    building_name = None

    # Exercise
    building = js_authenticated.get_building(building_name)
    building_stripped = js_authenticated.strip_extra_location_information(building)

    # Verify
    assert building_stripped is None

    # Cleanup - none

def test_get_sites(js_authenticated):
    # Setup - none

    # Exercise
    sites = js_authenticated.get_sites()

    # Verify
    assert len(sites) > 1

    # Cleanup - none

def test_get_site(js_authenticated):
    # Setup
    site_name = '***REMOVED***'
    desired_id = 5

    # Exercise
    site = js_authenticated.get_site(site_name)

    # Verify
    assert site['id'] == desired_id
    assert site['name'] == site_name

    # Cleanup - none

def test_flush_failed_mobile_device_commands(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID

    # Exercise
    response = js_authenticated.flush_mobile_device_commands(device_id, "Failed")

    # Verify
    assert response

    # Cleanup - none

def test_update_inventory(js_authenticated):
    # Setup
    device_id = TEST_DEVICE_ID
    desired_success = '<status>Command sent</status>'
    js_authenticated.flush_mobile_device_commands(device_id)
    time.sleep(0.25)

    # Exercise
    response = js_authenticated.update_inventory(device_id)

    # Verify
    assert desired_success in response


