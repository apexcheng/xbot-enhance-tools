from xbot import web, sleep

import random
import time

from .browser_utils import wait_appear_by_xpath

def login_pdd_seller(account, password, profile=None):
    """拼多多商家中心登录。

    :param str account: 账号
    :param str password: 密码
    :param str profile: Chrome profile 名（如 "Default" / "Profile 1"）；为空则不激活
    :return: bool, URL 不含 'login' 返回 True，含 'login' 返回 False
    """
    if profile:
        web.set_user_environment(mode="chrome", profile_name=profile)

    browser = web.create("https://mms.pinduoduo.com/login/", mode="chrome", load_timeout=20)

    browser.find_by_xpath("//div[contains(@class, 'info-part')]//div[contains(text(), '账号登录')]", timeout=10).click(delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, 'info-part')]//input[contains(@id, 'username')]", timeout=10).input(account, delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, 'info-part')]//input[contains(@id, 'password')]", timeout=10).input(password, delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, 'info-part')]//button[contains(., '登录')]/span", timeout=10).click(delay_after=0.5)

    # XPath 会随页面变化，需运行验证；这里通过跳转后的 URL 判断是否离开登录页。
    browser.wait_load_completed(timeout=60 * 2)
    sleep(2)
    return "login" not in browser.get_url()


def login_qianniu(account, password, profile=None):
    """千牛（淘宝/天猫商家工作台）登录。

    :param str account: 账号
    :param str password: 密码
    :param str profile: Chrome profile 名（如 "Default" / "Profile 1"）；为空则不激活
    :return: bool, URL 不含 'login' 返回 True，含 'login' 返回 False
    """
    from xbot_extensions import iframe2

    if profile:
        web.set_user_environment(mode="chrome", profile_name=profile)

    browser = web.create("https://loginmyseller.taobao.com/", mode="chrome", load_timeout=20)

    # browser.find_by_xpath("//div[contains(@class, 'login')]//a[contains(text(), '密码登录')]", timeout=10).click(delay_after=0.2)
    # browser.find_by_xpath("//form[contains(@class, 'login-form')]//input[contains(@id, 'login-id')]", timeout=10).input(account, delay_after=0.3)
    # browser.find_by_xpath("//form[contains(@class, 'login-form')]//input[contains(@id, 'password')]", timeout=10).input(password, delay_after=0.3)
    # browser.find_by_xpath("//form[contains(@class, 'login-form')]//button[contains(text(), '登录')]", timeout=10).click(delay_after=0.5)


    iframe_instance = iframe2.init_iframe(browser)
    iframe_page = iframe2.to_iframe(iframe_instance, "//iframe[contains(@id, 'login')]", False, "5")

    iframe2.click_by_xpath(iframe_page, "//div[contains(@class, 'login')]//a[contains(text(), '密码登录')]", False, True, False, "left", "none", 0, "单击", "10")
    iframe2.input_by_xpath(iframe_page, "//form[contains(@class, 'login-form')]//input[contains(@id, 'login-id')]", account, False, "模拟输入", False, False, 50, 5, 1, True, False, "10")
    iframe2.input_by_xpath(iframe_page, "//form[contains(@class, 'login-form')]//input[contains(@id, 'password')]", password, False, "模拟输入", False, False, 50, 5, 1, True, False, "10")
    iframe2.click_by_xpath(iframe_page, "//form[contains(@class, 'login-form')]//button[contains(text(), '登录')]", False, True, False, "left", "none", 0, "单击", "10")


    # XPath 会随页面变化，需运行验证；这里通过跳转后的 URL 判断是否离开登录页。
    browser.wait_load_completed(timeout=60 * 2)
    sleep(2)
    return "login" not in browser.get_url()


def login_jingmai(account, password, profile=None):
    """京麦（京东商家工作台）登录。

    :param str account: 账号
    :param str password: 密码
    :param str profile: Chrome profile 名（如 "Default" / "Profile 1"）；为空则不激活
    :return: bool, URL 不含 'login' 返回 True，含 'login' 返回 False
    """
    if profile:
        web.set_user_environment(mode="chrome", profile_name=profile)

    browser = web.create("https://passport.shop.jd.com/", mode="chrome", load_timeout=20)

    browser.find_by_xpath("//div[contains(@class, 'login')]//*[contains(text(), '密码登录')]", timeout=10).click(delay_after=0.2)
    browser.find_by_xpath("//div[contains(@class, 'login')]//input[contains(@id, 'loginname')]", timeout=10).input(account, delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, 'login')]//input[contains(@type, 'password')]", timeout=10).input(password, delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, 'login')]//button[contains(., '登录')]", timeout=10).click(delay_after=0.5)

    # XPath 会随页面变化，需运行验证；这里通过跳转后的 URL 判断是否离开登录页。
    browser.wait_load_completed(timeout=60 * 2)
    sleep(2)
    return "login" not in browser.get_url()


def login_alipay(account, password, profile=None):
    """支付宝登录。

    :param str account: 账号
    :param str password: 密码
    :param str profile: Chrome profile 名（如 "Default" / "Profile 1"）；为空则不激活
    :return: bool, URL 不含 'login' 返回 True，含 'login' 返回 False
    """
    if profile:
        web.set_user_environment(mode="chrome", profile_name=profile)

    browser = web.create("https://auth.alipay.com/login/index.htm", mode="chrome", load_timeout=20)
    sleep(random.randint(2, 5))

    browser.find_by_xpath("//div[contains(@class, ' authcenter-body-login')]//li[contains(text(), '账密登录')]", timeout=20).click(delay_after=0.3)
    browser.find_by_xpath("//div[contains(@class, ' authcenter-body-login')]//input[contains(@id, 'user')]", timeout=10).clipboard_input(account, delay_after=1, send_key_delay=100)
    browser.find_by_xpath("//div[contains(@class, ' authcenter-body-login')]//span[contains(@id, 'password')]/input", timeout=10).input(password, delay_after=1, send_key_delay=100)
    sleep(random.randint(1, 3))
    browser.find_by_xpath("//div[contains(@class, ' authcenter-body-login')]//input[contains(@id, 'login-simulate-btn')]", timeout=10).click(delay_after=0.5)

    for _ in range(10):
        # 有时候弹出风险，需要二次点击
        if not wait_appear_by_xpath(browser, "//div[contains(@class, ' authcenter-body-login')]//input[contains(@id, 'login-simulate-btn')]", timeout=3):
            browser.find_by_xpath("//div[contains(@class, ' authcenter-body-login')]//input[contains(@id, 'login-simulate-btn')]", timeout=10).click(delay_after=0)
            sleep(1)
        else:
            break

    # 支付宝可能出现扫码、安全验证、短信验证等中间页，这里只做基础跳转判断。
    browser.wait_load_completed(timeout=60 * 2)
    sleep(2)

    return "login" not in browser.get_url()


def login_douyin_seller(account, password, profile=None):
    """抖音店铺登录。

    :param str account: 邮箱账号
    :param str password: 密码
    :param str profile: Chrome profile 名称（如 "Default" / "Profile 1"）；为空则不激活
    :return: bool, URL 不包含 'login' 时返回 True
    """
    if profile:
        web.set_user_environment(mode="chrome", profile_name=profile)

    browser = web.create("https://fxg.jinritemai.com/login", mode="chrome", load_timeout=20)

    browser.find_by_xpath(
        "//div[contains(@class, 'daren-login-container')]//*[contains(text(), '邮箱登录')]",
        timeout=10,
    ).click(delay_after=0.3)
    browser.find_by_xpath(
        "//div[contains(@class, 'daren-login-container')]//input[@name='email']",
        timeout=10,
    ).input(account, delay_after=0.3)
    browser.find_by_xpath(
        "//div[contains(@class, 'daren-login-container')]//input[@name='password']",
        timeout=10,
    ).input(password, delay_after=0.3)

    unchecked_agreement = wait_appear_by_xpath(
        browser,
        '//div[contains(@class, "daren-login-container")]//span[contains(@class, "auxo-checkbox") and not(contains(@class, "auxo-checkbox-checked"))]/input',
        timeout=1,
    )
    if unchecked_agreement:
        unchecked_agreement.click(delay_after=0.3)

    browser.find_by_xpath(
        "//div[contains(@class, 'daren-login-container')]//button[contains(., '登录')]",
        timeout=10,
    ).click(delay_after=0.5)

    deadline = time.time() + 30
    while True:
        sleep(5)

        if "login" not in browser.get_url():
            return True

        if time.time() > deadline:
            raise TimeoutError("抖音店铺登录超时（30秒）")
