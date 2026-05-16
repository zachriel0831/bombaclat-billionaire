# 2026-05-14 - Healthcare public records for healthcare_burden

## Context
Healthcare burden needs official context beyond news articles: nursing staff, bed occupancy, hospital/clinic workforce, hospital bed capacity, nursing staff totals, and healthcare-related welfare/legal proposals.

## Decision
- Add CLI alias `healthcare` for the healthcare public-record source set.
- Store healthcare official rows in `t_public_records`, not `t_news_articles`.
- Use `category=society` and tag rows with `healthcare_burden` so issue views can query these records as social-policy context.
- Store healthcare-filtered Legislative Yuan proposals as a separate derived record type, `healthcare_legislative_bill`, instead of mutating generic `legislative_bill` rows.

## Source Mapping
- `ly_healthcare_bills` -> `source_id=ly`, `record_type=healthcare_legislative_bill`
- `nhi_hospital_nursing_staff` -> `source_id=nhi`, `record_type=nhi_hospital_nursing_staff_stat`
- `nhi_hospital_bed_occupancy` -> `source_id=nhi`, `record_type=nhi_hospital_bed_occupancy_stat`
- `mohw_hospital_workforce` -> `source_id=mohw`, `record_type=mohw_hospital_workforce_stat`
- `mohw_clinic_workforce` -> `source_id=mohw`, `record_type=mohw_clinic_workforce_stat`
- `mohw_hospital_beds` -> `source_id=mohw`, `record_type=mohw_hospital_bed_stat`
- `mohw_nursing_staff_stats` -> `source_id=mohw`, `record_type=mohw_nursing_staff_stat`

## Notes
- NHI monthly nursing-staff rows are aggregated by Gregorian year/month and county/city to keep the record set useful for trend analysis and avoid per-hospital volume spikes.
- MOHW annual township rows are aggregated by year and county/city.
- NHI bed-occupancy rows are stored per hospital because the official ODS does not include county/city and the row count is moderate.
- `healthcare_legislative_bill` is eligible for the existing LY deterministic matcher.
