import logging

logger = logging.getLogger(__name__)


def run(job):
    logger.info("job başladı: %s", job.id)
    do(job)
