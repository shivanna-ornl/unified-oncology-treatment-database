-- DOCUMENTATION: See README.md
-- This file creates all staging files for Regimens. 

create temporary sequence RegimenID7 start 1;

create temporary table Regimens7 (
	RegimenID7 INTEGER,
	RegimenName VARCHAR
);

-- Regimen Staging Table 7 (SEER RX)
create temporary table unnested_seerrx_regimens as
select DISTINCT
	lower(unnest(s.drugs)) as "drugs",
	lower(s.name) as "regimen",
	lower(unnest(s.alternate_names)) as "alternate_names"
from 
	TREATMENT.SRC_SEER_RX_REGIMENS as s;
--1768

INSERT INTO Regimens7
with ListRegimens as (
	select DISTINCT
		regimen as regimen,
	from 
		unnested_seerrx_regimens as s
) SELECT 
	nextval('RegimenID7') as RegimenID7,
	b.*
FROM 
	ListRegimens as b;
--467

INSERT INTO Regimens7
WITH ListRegimens AS (
	select DISTINCT 
		alternate_names as regimen
	from 
		unnested_seerrx_regimens as s
	where alternate_names NOT IN (
		SELECT 
			RegimenName
		from 
			Regimens7)
) select
	nextval('RegimenID7') as RegimenID7,
	b.*
FROM 
	ListRegimens as b;
--146

INSERT INTO FinalDrugs
WITH ListDrugs AS (
	select DISTINCT 
		drugs as drug
	FROM 
		unnested_seerrx_regimens 
	WHERE 
		drugs NOT IN (
			select 
				DrugName 
			from 
				FinalDrugs)
) SELECT 
	nextval('FinalDrugID') as FinalDrugID,
	b.*
FROM 
	ListDrugs as b;
--4

CREATE TEMPORARY TABLE source_7_preprocessing_regimens AS 
SELECT DISTINCT 
	r.RegimenID7 as "regimen_id",
	us.regimen as "regimen_name",
	us.alternate_names as "regimen_synonym",
	rr.RegimenID7 as "regimen_synonym_id",
	us.drugs as "anchor_drug",
	d.DrugID as "anchor_id",
	7 as source_id
FROM 
	unnested_seerrx_regimens as us
left join Regimens7 as r
	on us.regimen = r.RegimenName
left join Regimens7 as rr
	on us.alternate_names = rr.RegimenName
left join Drugs as d 
	on us.drugs = d.DrugName
where lower(us.alternate_names) != lower(us.regimen)
or alternate_names IS NULL;
--1768

update source_7_preprocessing_regimens
set regimen_synonym = 'none'
where regimen_synonym IS NULL;
--1622

update source_7_preprocessing_regimens
set regimen_synonym_id = 1000000
where regimen_synonym_id IS NULL;
--1622

create temporary sequence source_7_rowids_regimens start 1;

CREATE TEMPORARY TABLE source_7_regimens (
	source_7_rowids_regimens INTEGER,
	regimen_id INTEGER,
	regimen_name VARCHAR,
	regimen_synonym VARCHAR,
	regimen_synonym_id INTEGER,
	anchor_drug VARCHAR,
	anchor_id	INTEGER,
	source_id INTEGER
);


INSERT into source_7_regimens
with x as (
	select DISTINCT 
		*
	from 
		source_7_preprocessing_regimens
	where regimen_synonym_id not in (
		SELECT 
			regimen_id 
		from source_7_preprocessing_regimens)
	UNION
	--SWAP
	SELECT DISTINCT
		regimen_synonym_id,
		regimen_synonym,
		regimen_name,
		regimen_id,
		anchor_drug,
		anchor_id,
		source_id
	FROM 
		source_7_preprocessing_regimens
	WHERE regimen_synonym_id in (
		SELECT 
			regimen_id 
		from source_7_preprocessing_regimens)
) select 
	nextval('source_7_rowids_regimens') as source_7_rowids_regimens,
	x.*
from x;	
--1768

CREATE TEMPORARY TABLE source_7_circular_delete_regimen AS 
SELECT DISTINCT 
	f1.source_7_rowids_regimens,
	f1.regimen_name,
	f1.regimen_synonym,
	f1.source_id
FROM 
	source_7_regimens AS f1
JOIN 
	source_7_regimens AS f2
	ON
		f1.regimen_name = f2.regimen_synonym
	AND 
		f1.regimen_synonym = f2.regimen_name
	WHERE 
		f1.regimen_id > f1.regimen_synonym_id;
--0
	
delete from source_7_regimens
where source_7_rowids_regimens in (
	select 
		source_7_rowids_regimens
	from 
		source_7_circular_delete_regimen);	
--del 0

create temporary table source_7_swap_delete_regimens as
select DISTINCT 
	*
from 
	source_7_regimens
where
	regimen_id > regimen_synonym_id;
--0

delete from source_7_regimens
where source_7_rowids_regimens in (
	select 
		source_7_rowids_regimens
	from 
		source_7_swap_delete_regimens);
--del 0
	
insert into source_7_regimens	
select DISTINCT 
	source_7_rowids_regimens as 'source_7_rowids_regimens',
	regimen_synonym_id as 'regimen_id',
	regimen_synonym as 'regimen_name',
	regimen_name as 'regimen_synonym',
	regimen_id as 'regimen_synonym_id',
	anchor_drug as 'anchor_drug',
	anchor_id as 'anchor_id',
	source_id as 'source_id'
from 
	source_7_swap_delete_regimens;
--0
	
create temporary table source_7_staging_regimens as
select DISTINCT 
	regimen_name,
	anchor_drug,
	regimen_synonym,
	source_id
from 
	source_7_regimens;		
--1768

-- Source 1 Staging File (HEMONC)
create temporary sequence RegimenID1 start 1;

create temporary table Regimens1 (
	RegimenID1 INTEGER,
	RegimenName VARCHAR
);

INSERT INTO Regimens1
with ListRegimens as (
	select DISTINCT
		lower(concept_name) as regimen
	FROM
		TREATMENT.SRC_HEMONC_CONCEPT_STAGE 
	WHERE 
		domain_id = 'regimen'
	AND 
		invalid_reason IS NULL
) SELECT DISTINCT 
	nextval('RegimenID1') as RegimenID1,
	b.*
FROM 
	ListRegimens as b;
--7420

insert into Regimens1
with ListRegimens as (
	select DISTINCT 
		lower(s.synonym_name) as regimen
	FROM 
		TREATMENT.SRC_HEMONC_CONCEPT_SYNONYM_STAGE as s
	WHERE 
		s.invalid_reason IS NULL
	and lower(s.synonym_name) NOT IN (
		SELECT 
			RegimenName
		from 
			Regimens1)
) SELECT DISTINCT 
	nextval('RegimenID1') as RegimenID1,
	b.*
FROM 
	ListRegimens as b;
--104497


INSERT INTO FinalDrugs
WITH ListDrugs AS (
	select DISTINCT 
		lower(component) as drug
	FROM 
		TREATMENT.SRC_HEMONC_SIGS 
	WHERE 
		lower(component) NOT IN (
			select 
				DrugName 
			from 
				FinalDrugs)
) SELECT 
	nextval('FinalDrugID') as FinalDrugID,
	b.*
FROM 
	ListDrugs as b;
--33

CREATE TEMPORARY TABLE source_1_prep_regimens AS 
WITH hcs AS (
		SELECT 
			lower(concept_name) AS "regimen",
			concept_code,
			domain_id
		FROM
			TREATMENT.SRC_HEMONC_CONCEPT_STAGE 
		WHERE 
			domain_id = 'regimen'
		AND 
			invalid_reason IS NULL),
	hcss AS (
		SELECT DISTINCT 
			lower(synonym_name) AS "regimen_synonym",
			synonym_concept_code
		FROM 
			TREATMENT.SRC_HEMONC_CONCEPT_SYNONYM_STAGE
		WHERE 
			invalid_reason IS NULL
) SELECT DISTINCT 
	lower(c.regimen) AS "regimen",
	lower(h.component) AS "anchor_drug",
	lower(s.regimen_synonym) as "regimen_synonym",
	1 as source_id
FROM 
	TREATMENT.SRC_HEMONC_SIGS as h
LEFT JOIN hcs AS c
	ON lower(h.regimen) = lower(c.regimen)
LEFT JOIN hcss AS s
	ON c.concept_code = s.synonym_concept_code
WHERE 
	lower(c.regimen) != lower(s.regimen_synonym)
and 
	lower(h.component_role) like ('primary systemic');
--9866

create temporary table source_1_preprocessing_regimens as 
select DISTINCT 
	r.RegimenID1 as "regimen_id",
	s.regimen as "regimen_name",
	s.regimen_synonym,
	rr.RegimenID1 as "regimen_synonym_id",
	s.anchor_drug,
	d.FinalDrugID as "anchor_id",
	s.source_id
from source_1_prep_regimens as s
left join Regimens1 as r
	on lower(s.regimen) = r.RegimenName
left join Regimens1 as rr
	on lower(s.regimen_synonym) = rr.RegimenName
left join FinalDrugs as d 
	on lower(s.anchor_drug) = d.DrugName
where lower(s.regimen) != lower(s.regimen_synonym);
--9866

create temporary sequence source_1_rowids_regimens start 1;

CREATE TEMPORARY TABLE source_1_regimens (
	source_1_rowids_regimens INTEGER,
	regimen_id INTEGER,
	regimen_name VARCHAR,
	regimen_synonym VARCHAR,
	regimen_synonym_id INTEGER,
	anchor_drug VARCHAR,
	anchor_id	INTEGER,
	source_id INTEGER
);

INSERT into source_1_regimens
with x as (
	select DISTINCT 
		*
	from 
		source_1_preprocessing_regimens
	where regimen_synonym_id not in (
		SELECT 
			regimen_id 
		from source_1_preprocessing_regimens)
	UNION
	--SWAP
	SELECT DISTINCT
		regimen_synonym_id,
		regimen_synonym,
		regimen_name,
		regimen_id,
		anchor_drug,
		anchor_id,
		source_id
	FROM 
		source_1_preprocessing_regimens
	WHERE regimen_synonym_id in (
		SELECT 
			regimen_id 
		from source_1_preprocessing_regimens)
) select 
	nextval('source_1_rowids_regimens') as source_1_rowids_regimens,
	x.*
from x;	
--9866

CREATE TEMPORARY TABLE source_1_circular_delete_regimen AS 
SELECT DISTINCT 
	f1.source_1_rowids_regimens,
	f1.regimen_name,
	f1.regimen_synonym,
	f1.source_id
FROM 
	source_1_regimens AS f1
JOIN 
	source_1_regimens AS f2
	ON
		f1.regimen_name = f2.regimen_synonym
	AND 
		f1.regimen_synonym = f2.regimen_name
	WHERE 
		f1.regimen_id > f1.regimen_synonym_id;
--3
	
delete from source_1_regimens
where source_1_rowids_regimens in (
	select 
		source_1_rowids_regimens
	from 
		source_1_circular_delete_regimen);	
--del 3

create temporary table source_1_swap_delete_regimens as
select DISTINCT 
	*
from 
	source_1_regimens
where
	regimen_id > regimen_synonym_id;
--212

delete from source_1_regimens
where source_1_rowids_regimens in (
	select 
		source_1_rowids_regimens
	from 
		source_1_swap_delete_regimens);
--del 212
	
insert into source_1_regimens	
select DISTINCT 
	source_1_rowids_regimens as 'source_1_rowids_regimens',
	regimen_synonym_id as 'regimen_id',
	regimen_synonym as 'regimen_name',
	regimen_name as 'regimen_synonym',
	regimen_id as 'regimen_synonym_id',
	anchor_drug as 'anchor_drug',
	anchor_id as 'anchor_id',
	source_id as 'source_id'
from 
	source_1_swap_delete_regimens;
--212
	
create temporary table source_1_staging_regimens as
select DISTINCT 
	regimen_name,
	anchor_drug,
	regimen_synonym,
	source_id
from 
	source_1_regimens;		
--9863

-- This next section of code creates the final staging table for drugs
-- Create the shell table
create temporary sequence FinalRegimenID start 1;

create temporary table FinalRegimens (
	FinalRegimenID INTEGER,
	RegimenName VARCHAR
);

insert into FinalRegimens 
WITH ListRegimens AS (
	select DISTINCT 
		regimen_name
	FROM 
		source_7_staging_regimens
) SELECT 
	nextval('FinalRegimenID') as FinalRegimenID,
	b.*
FROM 
	ListRegimens as b;
--467

insert into FinalRegimens 
WITH ListRegimens AS (
	select DISTINCT 
		regimen_name
	FROM 
		source_1_staging_regimens
	where 
		regimen_name not in (
			select DISTINCT 
				RegimenName
			from 
				FinalRegimens)
) SELECT 
	nextval('FinalRegimenID') as FinalRegimenID,
	b.*
FROM 
	ListRegimens as b;
--1106

insert into FinalRegimens 
WITH ListRegimens AS (
	select DISTINCT 
		regimen_synonym
	FROM 
		source_7_staging_regimens
	where 
		regimen_synonym not in (
			select DISTINCT 
				RegimenName
			from 
				FinalRegimens)
) SELECT 
	nextval('FinalRegimenID') as FinalRegimenID,
	b.*
FROM 
	ListRegimens as b;
--118

insert into FinalRegimens 
WITH ListRegimens AS (
	select DISTINCT 
		regimen_synonym
	FROM 
		source_1_staging_regimens
	where 
		regimen_synonym not in (
			select DISTINCT 
				RegimenName
			from 
				FinalRegimens)
) SELECT 
	nextval('FinalRegimenID') as FinalRegimenID,
	b.*
FROM 
	ListRegimens as b;
--2744

create temporary sequence final_regimen_rowids start 1;

CREATE TEMPORARY TABLE Final_Regimen_Staging_Table (
	final_regimen_rowids INT,
	regimen_name VARCHAR,
	regimen_id INT,
	regimen_synonym VARCHAR,
	regimen_synonym_id INT,
	anchor_drug VARCHAR,
	anchor_id INT,
	source_id INT
);

INSERT INTO Final_Regimen_Staging_Table
with x as (
	SELECT DISTINCT 
		s7.regimen_name,
		fr.FinalRegimenID as "regimen_id",
		s7.regimen_synonym,
		frr.FinalRegimenID as "regimen_synonym_id",
		s7.anchor_drug,
		fd.FinalDrugID as "anchor_id",
		s7.source_id
	from 
		source_7_staging_regimens as s7
	LEFT JOIN FinalRegimens as fr
		on fr.RegimenName = s7.regimen_name
	LEFT JOIN FinalRegimens as frr
		on frr.RegimenName = s7.regimen_synonym
	LEFT JOIN FinalDrugs as fd
		on fd.DrugName = s7.anchor_drug
) select 
	nextval('final_regimen_rowids') as final_regimen_rowids,
	x.*
from x;
--1768

INSERT INTO Final_Regimen_Staging_Table
with x as (
	SELECT DISTINCT 
		s1.regimen_name,
		fr.FinalRegimenID as "regimen_id",
		s1.regimen_synonym,
		frr.FinalRegimenID as "regimen_synonym_id",
		s1.anchor_drug,
		fd.FinalDrugID as "anchor_id",
		s1.source_id
	from 
		source_1_staging_regimens as s1
	LEFT JOIN FinalRegimens as fr
		on fr.RegimenName = s1.regimen_name
	LEFT JOIN FinalRegimens as frr
		on frr.RegimenName = s1.regimen_synonym
	LEFT JOIN FinalDrugs as fd
		on fd.DrugName = s1.anchor_drug
	WHERE 
		regimen_synonym_id not in (
			select 
				regimen_id
			from 
				Final_Regimen_Staging_Table)
	UNION
		--SWAP
		SELECT DISTINCT
			s1.regimen_synonym,	
			frr.FinalRegimenID as 'regimen_synonym_id',
			s1.regimen_name,
			fr.FinalRegimenID as 'regimen_id',
			s1.anchor_drug,
			d.FinalDrugID as 'anchor_id',
			s1.source_id
		FROM source_1_preprocessing_regimens as s1
		LEFT JOIN FinalRegimens as fr
		on fr.RegimenName = s1.regimen_name
		LEFT JOIN FinalRegimens as frr
			on frr.RegimenName = s1.regimen_synonym
		LEFT JOIN FinalDrugs as d
			on d.DrugName = s1.anchor_drug
		WHERE regimen_synonym_id in (
			SELECT 
				anchor_id 
			from Final_Regimen_Staging_Table)
) select 
	nextval('final_rowids') as final_rowids,
	x.*
from x;
--9671

CREATE TEMPORARY TABLE final_circular_delete_regimen AS 
SELECT DISTINCT 
	f1.final_regimen_rowids,
	f1.regimen_name,
	f1.regimen_synonym,
	f1.regimen_synonym_id,
	f1.source_id
FROM 
	Final_Regimen_Staging_Table AS f1
JOIN 
	Final_Regimen_Staging_Table AS f2
	ON
		f1.regimen_name = f2.regimen_synonym
	AND 
		f1.regimen_synonym = f2.regimen_name
	WHERE 
		f1.regimen_id > f1.regimen_synonym_id;
--4
	
delete from Final_Regimen_Staging_Table
where final_regimen_rowids in (
	select 
		final_regimen_rowids
	from 
		final_circular_delete_regimen);	
--del 4

create temporary table final_swap_delete_regimens as
select DISTINCT 
	*
from 
	Final_Regimen_Staging_Table
where
	regimen_id > regimen_synonym_id;
--130

delete from Final_Regimen_Staging_Table
where final_regimen_rowids in (
	select 
		final_regimen_rowids
	from 
		final_swap_delete_regimens);
--del 130
		
insert into Final_Regimen_Staging_Table	
select DISTINCT 
	final_regimen_rowids as 'final_regimen_rowids',
	regimen_synonym as 'regimen_name',
	regimen_synonym_id as 'regimen_id',
	regimen_name as 'regimen_synonym',
	regimen_id as 'regimen_synonym_id',
	anchor_drug as 'anchor_drug',
	anchor_id as 'anchor_id',
	source_id as 'source_id'
from 
	final_swap_delete_regimens;
--130

create temporary table Regimen_Staging_Table as
select DISTINCT 
	*
from Final_Regimen_Staging_Table;

-- Total Count: 11,435
