"""The data lakehouse (Oct 17): every input the world model reads, stored once, indexed, and searchable.

Raw files are stored by content hash, with the text a parser extracted from them, the chunks that text is split into,
their keyword and semantic indexes, the entities and values each chunk mentions, the import bundles extracted from
them, and when each was ingested and when its events happened (data can arrive out of order). Storage sits behind
one interface (`LakeStore`); the SQLite backend keeps raw files on the volume and needs no other service.
Every table is partitioned by tenant (a client's silo): nothing crosses tenants.
"""
