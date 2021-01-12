import logging
from collections import Counter
from pathlib import Path
from typing import List, Set, Dict

from ..etl_stats import EtlTransformation, etl_stats
from ..._paths import STANDARD_VOCAB_DIR
from ...cdm import vocabularies
from ...cdm._schema_placeholders import VOCAB_SCHEMA
from ...database import Database
from ...util.io import get_all_files_in_dir
from ...util.table import table_is_empty, get_full_table_name

logger = logging.getLogger(__name__)

_SUPPORTED_DIALECTS = {
    'postgresql',
}

_STANDARD_VOCAB_TABLE_NAMES: List[str] = [
    vocabularies.BaseConcept.__tablename__,
    vocabularies.BaseConceptAncestor.__tablename__,
    vocabularies.BaseConceptClass.__tablename__,
    vocabularies.BaseConceptRelationship.__tablename__,
    vocabularies.BaseConceptSynonym.__tablename__,
    vocabularies.BaseDomain.__tablename__,
    vocabularies.BaseDrugStrength.__tablename__,
    vocabularies.BaseRelationship.__tablename__,
    vocabularies.BaseVocabulary.__tablename__,
]


class StandardVocabLoader:
    def __init__(self, db: Database, cdm):
        self._db = db
        self._dialect = db.engine.name
        self._cdm = cdm

        self._standard_vocab_files: Set[Path] = set()
        self._table_file_mapping: Dict[str, Path] = dict()

    def load_standard_vocabs(self) -> None:
        self._check_engine_support()
        self._check_vocab_tables_are_empty()
        self._standard_vocab_files = self._get_vocab_files()
        self._create_table_file_mapping()
        self._db.constraint_manager.drop_all_constraints()

        for table, vocab_file in self._table_file_mapping.items():
            full_table_name = get_full_table_name(table=table, schema=VOCAB_SCHEMA,
                                                  schema_map=self._db.schema_translate_map)
            logger.info(f'Inserting {vocab_file} into {full_table_name}')
            self._insert_vocab_file(full_table_name, vocab_file)

        self._db.constraint_manager.add_all_constraints()

    @staticmethod
    def _get_vocab_files() -> Set[Path]:
        if not STANDARD_VOCAB_DIR.exists():
            raise FileNotFoundError(f'standard vocabulary folder not found. '
                                    f'Expected at {STANDARD_VOCAB_DIR}')
        return set(get_all_files_in_dir(STANDARD_VOCAB_DIR))

    def _create_table_file_mapping(self) -> None:
        # Find the corresponding data file for each vocab table
        for table_name in _STANDARD_VOCAB_TABLE_NAMES:
            for vocab_file in self._standard_vocab_files:
                if vocab_file.stem.lower() == table_name:
                    self._table_file_mapping[table_name] = vocab_file
                    break
            else:
                raise FileNotFoundError(f'No corresponding file was found for table '
                                        f'"{table_name}" in folder {STANDARD_VOCAB_DIR}')

    def _insert_vocab_file(self, table: str, vocab_file: Path) -> None:
        # postgresql-specific implementation
        transformation_metadata = EtlTransformation(name=f'load_{vocab_file.stem}')
        connection = self._db.engine.raw_connection()
        try:
            cursor = connection.cursor()
            statement = f"COPY {table} FROM STDIN WITH DELIMITER E'\t' CSV HEADER QUOTE E'\b';"
            with vocab_file.open('rb') as f:
                cursor.copy_expert(sql=statement, file=f)
            transformation_metadata.insertion_counts += Counter({table: cursor.rowcount})
            cursor.close()
            connection.commit()
        finally:
            connection.close()
        transformation_metadata.end_now()
        etl_stats.add_transformation(transformation_metadata)

    def _check_vocab_tables_are_empty(self) -> None:
        # We require all vocabulary tables to be empty beforehand, to
        # avoid (time-consuming) accidental reloading.
        for table_name in _STANDARD_VOCAB_TABLE_NAMES:
            full_table_name = f'{VOCAB_SCHEMA}.{table_name}'
            table = self._db.base.metadata.tables.get(full_table_name)
            if table is None:
                raise ValueError(f'Missing table "{table_name}". Make sure all vocabulary '
                                 f'table classes have been added to your cdm module '
                                 f'before loading vocabularies.')
            if not table_is_empty(mapped_table=table, database=self._db):
                raise ValueError(f'Table "{table_name}" is not empty. Make sure all '
                                 f'vocabulary tables are empty before loading vocabularies.')

    def _check_engine_support(self) -> None:
        if self._dialect not in _SUPPORTED_DIALECTS:
            raise NotImplementedError(f'Standard vocabulary loading is not supported for '
                                      f'the {self._dialect} dialect')