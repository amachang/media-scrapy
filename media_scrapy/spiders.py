import json
from typing import Dict, List, Any, Union, Optional, Type, Iterator
from pathlib import Path
import re
from importlib.machinery import SourceFileLoader
import inspect
from os import path
import os
import scrapy
from scrapy.http import Request, FormRequest, Response
from media_scrapy.errors import MediaScrapyError
from media_scrapy.conf import (
    SiteConfigDefinition,
    SiteConfig,
    DownloadUrlCommand,
    SaveFileContentCommand,
    RequestUrlCommand,
)
from media_scrapy.items import DownloadUrlItem, SaveFileContentItem
from typeguard import typechecked


@typechecked
class MainSpider(scrapy.Spider):
    name = "main"

    def __init__(self, siteconf: Union[str, Path, Type[SiteConfigDefinition]]) -> None:
        super().__init__(siteconf=siteconf)

        if inspect.isclass(siteconf):
            site_conf_cls = siteconf
        else:
            if isinstance(siteconf, str):
                site_conf_path = Path(siteconf)
            else:
                assert isinstance(siteconf, Path)
                site_conf_path = siteconf

            site_conf_matches = re.search(f"(.*)\\.py$", site_conf_path.name)
            if site_conf_matches is None:
                raise MediaScrapyError(
                    f"Site config file must be a python file: {site_conf_path}"
                )

            if not site_conf_path.exists():
                raise MediaScrapyError(f"Site config file not found: {site_conf_path}")

            site_conf_modulename = site_conf_matches.group(1)
            site_conf_module_loader = SourceFileLoader(
                site_conf_modulename, str(site_conf_path)
            )

            try:
                site_conf_module = site_conf_module_loader.load_module()
            except SyntaxError as err:
                raise MediaScrapyError(
                    f"Invalid python syntax in site config: {site_conf_path}"
                ) from err

            site_conf_cls_candidates = list(
                filter(inspect.isclass, vars(site_conf_module).values())
            )

            def is_site_config_def(cls: Type) -> bool:
                assert hasattr(cls, "__name__")
                return re.search(r"SiteConfig", cls.__name__) is not None

            site_conf_cls_candidates = list(
                filter(is_site_config_def, site_conf_cls_candidates)
            )

            if len(site_conf_cls_candidates) < 1:
                raise MediaScrapyError(
                    f"Class not found in site config: {site_conf_path}"
                )

            if 1 < len(site_conf_cls_candidates):
                raise MediaScrapyError(
                    f"Too many classes in site config: {site_conf_cls_candidates}"
                )

            site_conf_cls = site_conf_cls_candidates[0]

        site_conf = site_conf_cls()
        self.config = SiteConfig(site_conf)

    def start_requests(self) -> Iterator[Request]:
        if self.config.needs_login:
            callback = self.login
        else:
            callback = self.parse
        yield Request(
            self.config.start_url,
            callback=callback,
            dont_filter=True,
            meta={"structure_path": [], "file_path": []},
        )

    def login(self, res: Response) -> Iterator[Request]:
        assert self.config.needs_login
        yield FormRequest(
            self.config.login.url,
            formdata=self.config.login.formdata,
            callback=self.parse_login,
        )

    def parse_login(self, res: Response) -> Iterator[Request]:
        yield Request(
            self.config.start_url,
            callback=self.parse,
            dont_filter=True,
            meta={"structure_path": [], "file_path": []},
        )

    def parse(
        self, res: Response
    ) -> Iterator[Union[Request, SaveFileContentItem, DownloadUrlItem]]:
        commands = self.config.get_url_commands(res)

        for command in commands:
            if isinstance(command, SaveFileContentCommand):
                yield SaveFileContentItem(
                    file_content=command.file_content,
                    file_path=path.abspath(
                        path.join(self.config.save_dir, command.file_path)
                    ),
                )

            elif isinstance(command, DownloadUrlCommand):
                yield DownloadUrlItem(
                    url=command.url,
                    file_path=path.abspath(
                        path.join(self.config.save_dir, command.file_path)
                    ),
                )

            elif isinstance(command, RequestUrlCommand):
                yield Request(
                    command.url_info.url,
                    callback=self.parse,
                    meta={"url_info": command.url_info},
                )

            else:
                assert False
