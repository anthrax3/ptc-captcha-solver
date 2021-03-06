import time
import string
import random
import datetime
import sys

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from strings import *
from pikapy.ptcexceptions import *
from requests import post, get
from pyvirtualdisplay import Display

BASE_URL = "https://club.pokemon.com/us/pokemon-trainer-club"

# endpoints taken from PTCAccount
SUCCESS_URLS = (
    'https://club.pokemon.com/us/pokemon-trainer-club/parents/email',  # This initially seemed to be the proper success redirect
    'https://club.pokemon.com/us/pokemon-trainer-club/sign-up/',  # but experimentally it now seems to return to the sign-up, but still registers
)

# As both seem to work, we'll check against both success destinations until I have I better idea for how to check success
DUPE_EMAIL_URL = 'https://club.pokemon.com/us/pokemon-trainer-club/forgot-password?msg=users.email.exists'
BAD_DATA_URL = 'https://club.pokemon.com/us/pokemon-trainer-club/parents/sign-up'

POST_CAPTCHA_URL = "http://2captcha.com/in.php?key=@&method=userrecaptcha&googlekey=@&pageurl=@"
GET_CAPTCHA_URL = "http://2captcha.com/res.php?key=@&action=get&id=@"
FROM_CAPTCHA_URL = 'https://club.pokemon.com/us/pokemon-trainer-club/parents/email'

def _random_string(length=15):
    return generate_words(3)

def _random_email(local_length=10, sub_domain_length=5, top_domain=".com"):
    return "{local}@{sub_domain}{top_domain}".format(
        local=_random_string(local_length),
        sub_domain=_random_string(sub_domain_length),
        top_domain=top_domain
    )


def _random_birthday():
    """
    Creates a birthday between 1980 and 1990
    :return: string
    """
    start = datetime.datetime(1980, 1, 1)
    end = datetime.datetime(1990, 12, 31)

    diff = end - start

    random_duration = random.randint(0, diff.total_seconds())

    birthday = start + datetime.timedelta(seconds=random_duration)

    return "{year}-{month:0>2}-{day:0>2}".format(year=birthday.year, month=birthday.month, day=birthday.day)


def _validate_birthday(birthday):
    # raises PTCInvalidBirthdayException if invalid
    # split by -
    # has to be at least 2002 and after 1910
    # char length 10
    try:
        assert len(birthday) == 10

        # Ensure birthday is delimited by -
        # Ensure birthday is zero-padded
        year, month, day = birthday.split("-")
        assert year is not None and month is not None and day is not None
        assert len(year) == 4 and year.isdigit()
        assert len(month) == 2 and month.isdigit()
        assert len(day) == 2 and day.isdigit()

        # Check year is between 1910 and 2002, and also that it's a valid date
        assert datetime.datetime(year=1910, month=1, day=1) <= datetime.datetime(year=int(year), month=int(month), day=int(day)) <= datetime.datetime(year=2002, month=12, day=31)

    except (AssertionError, ValueError):
        raise PTCInvalidBirthdayException("Invalid birthday!")
    else:
        return True


def _validate_password(password):
    # Check that password length is between 6 and 15 characters long
    if len(password) < 6 or len(password) > 15:
        raise PTCInvalidPasswordException('Password must be between 6 and 15 characters.')
    return True
#http://2captcha.com/res.php?key=@&action=get&id=@
def captcha_handler(api_key,recaptcha_key):
    solution = ""
    print "Getting Captcha solved..."
    posted = POST_CAPTCHA_URL.split("@")
    FULL_POST_CAPTCHA_URL = posted[0]+api_key+posted[1]+recaptcha_key+posted[2]+FROM_CAPTCHA_URL
    answer = get(FULL_POST_CAPTCHA_URL).text
    i = 0
    
    if "|" in answer :
        CAPTCHA_ID = answer.split("|")[1]
    else:
        print "Something is not ok!"
        print answer
        sys.exit()
    posted = GET_CAPTCHA_URL.split("@")
    FULL_GET_CAPTCHA_URL = posted[0]+api_key+posted[1]+CAPTCHA_ID
    while solution == "":
        solution = get(FULL_GET_CAPTCHA_URL).text
        if "|" in solution :
            print "Solution found!"
            return solution.split("|")[1]
        else :
            solution = ""
            #print "Not solved yet!"
            time.sleep(1)
            i = i+1
            if i > 300:
                print "Error while resolving the captcha!Timeout 300 sec "
                sys.exit()
    
def create_account(username, password, email, birthday, api_key, headless):
    """
    As per PTCAccount by jepayne1138, this function raises:
      PTCInvalidNameException: If the given username is already in use.
      PTCInvalidPasswordException: If the given password is not a valid
        password that can be used to make an account. (Currently just
        validates length, so this means the given password was not between
        6 and 15 characters long.)
      PTCInvalidEmailException: If the given email was either in an invalid
        format (i.e. not local@subdomain.domain) or the email is already
        registered to an existing account.
      PTCInvalidStatusCodeException: If an invalid status code was received
        at any time. (Server or underlying code issue; try again and submit
        bug report on continues failure if creation works in browser.)
      AssertionError: If something a URL is not as expected
    This function returns true if account was created. Raises exceptions rather than returning false.
    """
    
    captcha_solution = ""
    
    if password is not None:
        _validate_password(password)

    print("Attempting to create user {user}:{pw}. Opening browser...".format(user=username, pw=password))
    if headless == 1:
        display = Display(visible=0, size=(800,600))
        display.start()
    driver = webdriver.Chrome()
    driver.set_window_size(600, 600)

    # Input age: 1992-01-08
    print("Step 1: Verifying age using birthday: {}".format(birthday))
    driver.get("{}/sign-up/".format(BASE_URL))
    assert driver.current_url == "{}/sign-up/".format(BASE_URL)
    elem = driver.find_element_by_name("dob")

    # Workaround for different region not having the same input type
    driver.execute_script("var input = document.createElement('input'); input.type='text'; input.setAttribute('name', 'dob'); arguments[0].parentNode.replaceChild(input, arguments[0])", elem)

    elem = driver.find_element_by_name("dob")
    elem.send_keys(birthday)
    elem.submit()
    # Todo: ensure valid birthday

    # Create account page
    print("Step 2: Entering account details")
    assert driver.current_url == "{}/parents/sign-up".format(BASE_URL)

    user = driver.find_element_by_name("username")
    user.clear()
    user.send_keys(username)

    elem = driver.find_element_by_name("password")
    elem.clear()
    elem.send_keys(password)

    elem = driver.find_element_by_name("confirm_password")
    elem.clear()
    elem.send_keys(password)

    elem = driver.find_element_by_name("email")
    elem.clear()
    elem.send_keys(email)

    elem = driver.find_element_by_name("confirm_email")
    elem.clear()
    elem.send_keys(email)

    driver.find_element_by_id("id_public_profile_opt_in_1").click()
    driver.find_element_by_name("terms").click()
    
    #2captcha handling starts here
    recaptcha_key = driver.find_element_by_class_name("g-recaptcha").get_attribute("data-sitekey")
    #print recaptcha_key
    captcha_solution = captcha_handler(api_key,recaptcha_key)
    
    # Now to handle captcha
    #print("Waiting; Please enter the captcha in the browser window...")
    
    #elem = driver.find_element_by_class_name("g-recaptcha")
    #driver.execute_script("arguments[0].scrollIntoView(true);", elem)

    # Waits 1 minute for you to input captcha
    #WebDriverWait(driver, 60).until(EC.text_to_be_present_in_element_value((By.ID, "g-recaptcha-response"), ""))
    #print("Captcha successful. Sleeping for 1 second...")
    #time.sleep(1)
    
    elem = driver.find_element_by_id("g-recaptcha-response")
    driver.execute_script("$('.g-recaptcha-response').css('display','block');")
    elem.clear()
    elem.send_keys(captcha_solution)
    
    try:
        user.submit()
    except StaleElementReferenceException:
        print("Error StaleElementReferenceException!")

    try:
        _validate_response(driver)
    except:
        print("Failed to create user: {}".format(username))
        raise

    print("Account successfully created.")
    driver.close()
    if headless == 1:
        display.stop()
    return True


def _validate_response(driver):
    url = driver.current_url
    if url in SUCCESS_URLS:
        return True
    elif url == DUPE_EMAIL_URL:
        raise PTCInvalidEmailException("Email already in use.")
    elif url == BAD_DATA_URL:
        if "Enter a valid email address." in driver.page_source:
            raise PTCInvalidEmailException("Invalid email.")
        else:
            raise PTCInvalidNameException("Username already in use.")
    else:
        raise PTCException("Generic failure. User was not created.")


def random_account(username=None, password=None, email=None, birthday=None, api_key=None, headless=0):
    try_username = _random_string() if username is None else str(username)
    password = _random_string() if password is None else str(password)
    try_email = _random_email() if email is None else str(email)
    try_birthday = _random_birthday() if birthday is None else str(birthday)

    if birthday is not None:
        _validate_birthday(try_birthday)

    account_created = False
    while not account_created:
        try:
            account_created = create_account(try_username, password, try_email, try_birthday, api_key, headless)
        except PTCInvalidNameException:
            if username is None:
                try_username = _random_string()
            else:
                raise
        except PTCInvalidEmailException:
            if email is None:
                try_email = _random_email()
            else:
                raise

    return {
        "username": try_username,
        "password": password,
        "email": try_email
    }
