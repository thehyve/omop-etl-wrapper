from collections import Counter
from datetime import datetime, timedelta

import pytest
from src.delphyne.model.etl_stats import EtlStats, EtlSource, EtlTransformation

from tests.python.model.etl_stats.conftest import get_etltransformation


@pytest.fixture(scope="module")
def etl_source() -> EtlSource:
    start = datetime(year=2025, month=1, day=1, hour=0, minute=0)
    end = datetime(year=2025, month=1, day=1, hour=0, minute=2)
    return EtlSource(start=start, end=end, source_name='source1', n_rows=50)


def test_duration(etl_source: EtlSource):
    assert etl_source.duration == timedelta(seconds=120)


def test_etlsource_to_dict(etl_source: EtlSource):
    assert etl_source.to_dict() == {
        'duration': timedelta(seconds=120),
        'end': datetime(2025, 1, 1, 0, 2),
        'n_rows': 50,
        'source_name': 'source1',
        'start': datetime(2025, 1, 1, 0, 0)
    }


@pytest.fixture(scope="module")
def etl_transformation() -> EtlTransformation:
    start = datetime(year=2025, month=1, day=1, hour=0)
    end = datetime(year=2025, month=1, day=1, hour=2)
    return EtlTransformation(start=start, end=end, name='T1000', query_success=True,
                             insertion_counts=Counter({'table1': 25, 'table2': 50}),
                             update_counts=Counter({'table1': 10}))


def test_etltransformation_to_dict(etl_transformation: EtlTransformation):
    assert etl_transformation.to_dict() == {
        'name': 'T1000',
        'query_success': True,
        'start': datetime(2025, 1, 1, 0, 0),
        'end': datetime(2025, 1, 1, 2, 0),
        'duration': timedelta(hours=2),
        'insertion_counts': 'table1:25, table2:50',
        'update_counts': 'table1:10',
        'deletion_counts': None,
    }


def test_transformation_is_vocab_only():
    t1 = get_etltransformation(name='vocab_only', insertion_counts=Counter({'concept': 950}))
    assert t1.is_vocab_only
    t2 = get_etltransformation(name='mixed',
                               insertion_counts=Counter({'concept': 950, 'person': 10}))
    assert not t2.is_vocab_only


def test_transformation_is_empty():
    t1 = get_etltransformation(name='empty')
    assert t1.is_empty
    t2 = get_etltransformation(name='not_empty', insertion_counts=Counter({'person': 10}))
    assert not t2.is_empty


@pytest.fixture(scope='module')
def etl_stats(etl_source: EtlSource, etl_transformation: EtlTransformation) -> EtlStats:
    stats = EtlStats()
    stats.add_source(etl_source)
    stats.add_transformation(etl_transformation)
    stats.add_transformation(get_etltransformation(name='failed_transformation',
                                                   query_success=False))
    stats.add_transformation(get_etltransformation(name='T2',
                                                   insertion_counts=Counter({'table2': 950})))
    return stats


def test_etlstats_lengths(etl_stats: EtlStats):
    assert len(etl_stats.sources) == 1
    assert etl_stats.n_queries_executed == 3
    assert len(etl_stats.successful_transformations) == 2


def test_total_insertions(etl_stats: EtlStats):
    assert etl_stats.total_insertions == Counter({'table2': 1000, 'table1': 25})


def test_total_duration(etl_stats: EtlStats):
    assert etl_stats.get_total_duration(etl_stats.transformations) == timedelta(hours=4)
