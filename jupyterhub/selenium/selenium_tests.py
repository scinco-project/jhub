#replace these
url = 'https://designsafe.jupyterhub.staging.tacc.cloud/'
users = [
('test1', 'p@ssw0rd'),
('test2', 'p@ssw0rd'),
]

import os

from kubernetes import client
from pprint import pprint
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')


def login(driver, user):
    driver.find_element_by_xpath("/html/body/div[1]/div/a").click()
    # agave oauth page
    username = driver.find_element_by_id("username")
    username.clear()
    username.send_keys(user['username'])
    pw = driver.find_element_by_id("password")
    pw.clear()
    pw.send_keys(user['password'])
    pw.send_keys(Keys.RETURN)
    # agave approve always page
    try:
        driver.find_element_by_id("approveAlways").click()
    except NoSuchElementException as e:
        # print('{} Is there an agave profile info request page? {} {} '.format(user['username'],e,driver.page_source))
        pass


def submit_form(driver):
    try:
        select = Select(driver.find_element_by_name('image'))
        select.select_by_index('0')
        submit_button = driver.find_element_by_xpath("/html/body/div[1]/div[2]/form/input")
        submit_button.click()
        WebDriverWait(driver, 100).until(
            EC.staleness_of(submit_button))
    except TimeoutException as e:
        print('What happened here {} '.format(driver.page_source))


def get_more_info(driver, user):
    try:
        WebDriverWait(driver, 280).until(
            EC.presence_of_element_located((By.ID, 'refresh_notebook_list')))
        print('{} notebook spawned successfully'.format(user['username']))
    except TimeoutException as e:  # notebook didn't spin up
        print('What happened here {} '.format(driver.page_source))
        with open('/run/secrets/kubernetes.io/serviceaccount/token') as f:
            token = f.read()
        with open('/run/secrets/kubernetes.io/serviceaccount/namespace') as f:
            namespace = f.read()

        configuration = client.Configuration()
        configuration.api_key['authorization'] = 'Bearer {}'.format(token)
        configuration.host = 'https://kubernetes.default'
        configuration.ssl_ca_cert = '/run/secrets/kubernetes.io/serviceaccount/ca.crt'

        api_instance = client.CoreV1Api(client.ApiClient(configuration))

        try:
            api_response = api_instance.read_namespaced_pod('jupyter-{}'.format(user['username']), namespace)
            pprint('😡 read_namespaced_pod {}'.format(str(api_response)))
        except Exception as e:
            pprint("Exception when calling CoreV1Api->read_namespaced_pod: %s\n" % e)

        try:
            api_response = api_instance.read_namespaced_pod_log('jupyter-{}'.format(user['username']), namespace)
            pprint('😡 {} read_namespaced_pod_log'.format(str(api_response)))
        except Exception as e:
            pprint("Exception when calling CoreV1Api->read_namespaced_pod_log: %s\n" % e)


for account in users:
    user = {
        'username':account[0],
        'password':account[1],
    }
    driver = webdriver.Chrome('{}/chromedriver'.format(os.path.dirname(os.path.realpath(__file__))), options=chrome_options)
    driver.get(url)
    login(driver, user)
    try:
        submit_form(driver)
    except NoSuchElementException as e:
        try:
            driver.find_element_by_id('refresh_notebook_list')
            print("{}'s notebook is already running".format(user['username']))
            continue
        except NoSuchElementException as e: #there's no options form
            print("{} has no options form".format(user['username']))
    except Exception as e:
        print('😱{} {} What happened here {}'.format(user['username'], e, driver.page_source))
    get_more_info(driver, user)
    driver.quit()
