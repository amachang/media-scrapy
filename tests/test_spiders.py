import pytest
from typing import List, Any
from os import path
from .utils import fake_spider, fake_response
from pathlib import Path
from media_scrapy.spiders import *
from media_scrapy.conf import SiteConfig
from media_scrapy.errors import MediaScrapyError
from media_scrapy.items import DownloadUrlItem, SaveFileContentItem
from scrapy.http import Request, FormRequest
from typeguard import TypeCheckError


def test_main_spider_init() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        save_dir = "/tmp"
        structure: List[Any] = []

    MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef))


def test_main_spider_start_requests() -> None:
    class SiteConfigDef000:
        start_url = "http://example.com/"
        save_dir = "/tmp"
        structure: List[Any] = []

    spider = MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef000))
    req = next(spider.start_requests())
    assert req.url == "http://example.com/"
    assert req.callback == spider.parse

    class SiteConfigDef001:
        start_url = "http://example.com/"
        login = {
            "url": "http://example.com/login",
            "formdata": {
                "user": "foo",
                "password": "bar",
            },
        }
        save_dir = "/tmp"
        structure: List[Any] = []

    spider = MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef001))
    req = next(spider.start_requests())
    assert req.url == "http://example.com/"
    assert req.callback == spider.login


def test_main_spider_login() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        login = {
            "url": "http://example.com/login",
            "formdata": {
                "user": "foo",
                "password": "bar",
            },
        }
        save_dir = "/tmp"
        structure: List[Any] = []

    spider = MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef))
    res = fake_response()
    req = next(spider.login(res))
    assert isinstance(req, FormRequest)
    assert req.url == "http://example.com/login"
    assert req.body in {b"user=foo&password=bar", b"password=bar&user=foo"}
    assert req.callback == spider.parse_login

    login_res = fake_response(request=req)
    after_login_req = next(spider.parse_login(res))
    assert after_login_req.url == "http://example.com/"
    assert after_login_req.callback == spider.parse


def test_main_spider_parse() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        save_dir = "/tmp"
        structure: List[Any] = [
            r"http://example\.com/",
            {
                "url": r"http://example\.com/\w+_dir",
                "file_path": lambda res: res.xpath("//title/text()").get(
                    default="unknown"
                ),
            },
            r"http://example\.com/\w+_dir/noname_dir",
            {
                "url": r"http://example\.com/files/(\w+\.txt)",
                "file_path": r"\g<1>",
            },
        ]

    spider = MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef))
    res = fake_response(body=b"<a href='/aaa_dir'>dir1</a><a href='/bbb_dir'>dir1</a>")
    results = list(spider.parse(res))
    assert len(results) == 2
    a_req, b_req = results

    assert isinstance(a_req, Request)
    assert a_req.callback == spider.parse
    assert a_req.url == "http://example.com/aaa_dir"
    assert a_req.meta["url_info"].structure_path == [0, 0]
    assert a_req.meta["url_info"].file_path == ""

    a_res = fake_response(
        request=a_req,
        body=b"<a href='/aaa_dir/xxx'>link1</a><a href='/aaa_dir/xxx'>link2</a>",
    )

    results = list(spider.parse(a_res))
    len(results) == 0

    assert isinstance(b_req, Request)
    assert b_req.callback == spider.parse
    assert b_req.url == "http://example.com/bbb_dir"
    assert b_req.meta["url_info"].structure_path == [0, 0]
    assert b_req.meta["url_info"].file_path == ""

    b_res = fake_response(
        request=b_req,
        body=b"<title>foo</title><a href='/bbb_dir/noname_dir'>link1</a><a href='/bbb_dir/noname_dir'>link2</a>",
    )

    results = list(spider.parse(b_res))
    assert len(results) == 1
    a_req = results[0]

    assert isinstance(a_req, Request)
    assert a_req.callback == spider.parse
    assert a_req.url == "http://example.com/bbb_dir/noname_dir"
    assert a_req.meta["url_info"].structure_path == [0, 0, 0]
    assert a_req.meta["url_info"].file_path == "foo"

    res = fake_response(
        request=a_req,
        body=b"<a href='/files/aaa.txt'>link1</a><a href='/files/bbb.txt'>link2</a><a href='/files/ccc.txt'>link3</a>",
    )
    results = list(spider.parse(res))
    assert len(results) == 3
    assert all(isinstance(item, DownloadUrlItem) for item in results)
    assert [item["url"] for item in results] == [
        "http://example.com/files/aaa.txt",
        "http://example.com/files/bbb.txt",
        "http://example.com/files/ccc.txt",
    ]
    assert [item["file_path"] for item in results] == [
        "/tmp/foo/aaa.txt",
        "/tmp/foo/bbb.txt",
        "/tmp/foo/ccc.txt",
    ]


def test_debug_spider_get_start_request_before_login() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        login = "http://example.com/login"
        save_dir = "/tmp"
        structure: List[Any] = []

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/aaa",
        choose_structure_definitions_callback=lambda *args: 0,
        start_debug_callback=lambda user_ns: None,
    )

    req = spider.get_start_request_before_login()
    assert req.url == "http://example.com/"


def test_debug_spider_login() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        login = "http://example.com/login"
        save_dir = "/tmp"
        structure: List[Any] = []

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/aaa",
        choose_structure_definitions_callback=lambda *args: 0,
        start_debug_callback=lambda user_ns: None,
    )

    res = fake_response()
    reqs = list(spider.login(res))
    assert len(reqs) == 1
    req = reqs[0]
    assert req.url == "http://example.com/login"


def test_debug_spider_get_first_request() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        login = "http://example.com/login"
        save_dir = "/tmp"
        structure: List[Any] = [
            {
                "url": r"http://example\.com/",
            },
            [
                [
                    {
                        "url": r"http://example\.com/(\w+)",
                        "as_url": "http://example.com/\g<1>_1",
                    },
                ],
                [
                    {
                        "url": r"http://example\.com/aaa",
                        "as_url": "http://example.com/aaa_2",
                    },
                ],
            ],
        ]

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/aaa",
        choose_structure_definitions_callback=lambda *args: 1,
        start_debug_callback=lambda user_ns: None,
    )

    req = spider.get_first_request()
    assert req.url == "http://example.com/aaa_2"

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/bbb",
        choose_structure_definitions_callback=lambda *args: 1,
        start_debug_callback=lambda user_ns: None,
    )

    req = spider.get_first_request()
    assert req.url == "http://example.com/bbb_1"

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/not-matched",
        choose_structure_definitions_callback=lambda *args: 1,
        start_debug_callback=lambda user_ns: None,
    )

    with pytest.raises(MediaScrapyError):
        spider.get_first_request()


def test_debug_spider_parse() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        login = "http://example.com/login"
        save_dir = "/tmp"
        structure: List[Any] = [
            {
                "url": r"http://example\.com/",
            },
            [
                [
                    {
                        "url": r"http://example\.com/(\w+)",
                        "as_url": "http://example.com/\g<1>_1",
                    },
                ],
                [
                    {
                        "url": r"http://example\.com/aaa",
                        "as_url": "http://example.com/aaa_2",
                    },
                ],
            ],
        ]

    called = False

    def debug_callback(user_ns: Dict[str, Any]) -> None:
        nonlocal called
        called = True

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/aaa",
        choose_structure_definitions_callback=lambda *args: 1,
        start_debug_callback=debug_callback,
    )

    res = fake_response()
    spider.parse(res)
    assert called


def test_get_first_request() -> None:
    class SiteConfigDef:
        start_url = "http://example.com/"
        save_dir = "/tmp"
        structure = [
            {
                "url": r"http://example\.com/",
            },
            {
                "url": r"http://example\.com/aaa",
            },
        ]

    spider = MainSpider(config=SiteConfig.create_by_definition(SiteConfigDef))
    request = spider.get_first_request()
    assert request.url == "http://example.com/"
    assert request.callback == spider.parse
    assert request.dont_filter == True

    def dummy_callback(user_ns: Dict[str, Any]) -> None:
        pass

    spider = DebugSpider(
        config=SiteConfig.create_by_definition(SiteConfigDef),
        debug_target_url="http://example.com/aaa",
        choose_structure_definitions_callback=lambda *args: 0,
        start_debug_callback=dummy_callback,
    )
    request = spider.get_first_request()
    assert request.url == "http://example.com/aaa"
    assert request.callback == spider.parse
