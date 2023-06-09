from pathlib import Path
from scrapy.settings import Settings
from scrapy.crawler import CrawlerRunner
from media_scrapy import settings as setting_definitions
from media_scrapy.spiders import MainSpider, DebugSpider
from twisted.python.failure import Failure
from scrapy.utils.log import configure_logging
from typing import Union, Type, Any, Optional, List, Dict, cast
import traceback
from typeguard import typechecked
from twisted.internet.defer import Deferred
from twisted.internet.error import ReactorNotRunning
from media_scrapy.conf import SiteConfig, SiteConfigDefinition
import click
import functools

import asyncio
from twisted.internet import asyncioreactor
from twisted.internet.base import ReactorBase
from scrapy.utils.reactor import install_reactor

install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")


@click.command
@click.option("--site-config", "-c", "site_config_path", type=Path, required=True)
@click.option("--verbose", "-v", "verbose", is_flag=True)
@click.option("--check-url", "-u", "debug_target_url", type=str, required=False)
def main_command(
    site_config_path: Path, verbose: bool, debug_target_url: Optional[str]
) -> None:
    d = main(site_config_path, verbose, debug_target_url)
    run_until_done(d)


@typechecked
def main(
    site_config_cls_or_path: Union[Path, Type],
    verbose: bool,
    debug_target_url: Optional[str],
) -> Deferred:
    configure_logging()
    settings = Settings()
    settings.setmodule(setting_definitions, priority="project")
    crawler = CrawlerRunner(settings)
    config = SiteConfig.create_by_definition(site_config_cls_or_path)

    if debug_target_url is None:
        crawler.settings.setdict(
            {
                "LOG_LEVEL": "DEBUG" if verbose else "INFO",
            },
            priority="cmdline",
        )
        d = crawler.crawl(MainSpider, config=config)
    else:
        crawler.settings.setdict(
            {
                "LOG_LEVEL": "INFO",  # DEBUG log is annoying during interactive shell
                "LOGSTATS_INTERVAL": 1440,  # 1440 min, almost not showing logs
            },
            priority="cmdline",
        )
        d = crawler.crawl(
            DebugSpider,
            config=config,
            debug_target_url=debug_target_url,
            choose_structure_definitions_callback=choose_structure_definitions,
            start_debug_callback=start_debug_repl,
        )
    return cast(Deferred, d)


@typechecked
def choose_structure_definitions(structure_description_list: List[str]) -> int:
    assert 0 < len(structure_description_list)
    prompt_message = ""
    structure_count = len(structure_description_list)
    for index, description in enumerate(structure_description_list):
        structure_number = index + 1
        prompt_message += f"[{structure_number}] {description}"
    prompt_message += "Choose structure for debug"

    choosed_number = cast(
        int, click.prompt(prompt_message, type=click.IntRange(1, structure_count))
    )
    return choosed_number - 1


@typechecked
def start_debug_repl(user_ns: Dict[str, Any]) -> None:
    # The implementation of ipython does not allow execution in a running event loop, so create a thread
    from threading import Thread

    ipython_thread = Thread(target=start_ipython_process, args=[user_ns])
    ipython_thread.start()
    ipython_thread.join()


@typechecked
def start_ipython_process(user_ns: Dict[str, Any]) -> None:
    # lazy import so as to mockable
    from IPython import start_ipython
    from traitlets.config.loader import Config

    # XXX I don't know proper way to do this
    config = Config()
    config.TerminalInteractiveShell.banner2 = user_ns["banner_message"]

    start_ipython(argv=[], user_ns=user_ns, config=config)


@typechecked
def run_until_done(d: Deferred) -> None:
    # lazy import so as to mockable
    import twisted.internet.reactor

    reactor = cast(ReactorBase, twisted.internet.reactor)

    result = None

    def callback(r: Any) -> None:
        nonlocal result
        result = r
        try:
            reactor.stop()
        except ReactorNotRunning:
            pass

    d.addBoth(callback)

    if not d.called:
        reactor.run()

    if result is not None and isinstance(result, Failure):
        failure = result
        if isinstance(failure.value, BaseException):
            traceback.print_exception(
                type(failure.value), failure.value, tb=failure.getTracebackObject()
            )
        failure.raiseException()


if __name__ == "__main__":
    main_command()
