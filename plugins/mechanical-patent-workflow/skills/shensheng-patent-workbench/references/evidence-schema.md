# 统一证据结构

案件中的 `evidence/evidence.json` 是 Excel、Word 和 PDF 的共同事实源。空白表示未核；数值 0 只表示已核后为零。

## 核心对象

### case

`case_id, case_type, subtype, title, decision_question, confidentiality, rights_jurisdictions[], search_authorities[], search_markets[], critical_date, data_cutoff, depth, deliverables[]`

这里只放不可变案件元数据；动态阶段、查询锁和回退批准以案件根目录的 `case.json` 为唯一权威源。

### targets

`target_id, target_type, identifier, claim_version, product_variant, source_file, source_sha256`

### features

`feature_id, target_id, claim_no, parent_feature_id, feature_text, normalized_text, category, necessary, interpretation, input_source_locator, amendment_support_locator`

机械 `category`：`object, component, connection, relative_position, motion_state, assembly_state, force_path, power_path, medium_path, control_logic, parameter, technical_effect`。

### search_runs

`run_id, round_id, purpose, engine, paid_command, database, market, jurisdiction_filter, query_original, query_normalized, query_hash, filters, executed_at, cache_hit, result_count, truncated, observability_rate, status, error, credits_charged, elapsed_seconds`

`query_original` 只允许写入权限为 `0600` 的显式案件证据文件和最终检索日志，用于复核；不得写入 `case.json.route_lock`、隐式缓存、命令参数或调用日志。路由锁只保存 HMAC `query_hash`。

`paid_command` 在 PatSeek 调用中为 `bool|semantic|patent`，并与 HMAC 预留及实际执行一致。`status` 只能是 `planned|success|partial|failed|timeout|blocked|uncertain`。失败、超时和不确定不得写成 0 命中；`timeout/uncertain` 必须先核对服务端任务或扣费状态才能重试。

### documents

`doc_id, publication_number, application_number, family_id, jurisdiction, document_kind, title, applicant_raw, applicant_normalized, priority_date, filing_date, publication_date, grant_date, source_engine, source_url, official_url, pdf_path, docx_path, file_sha256, retrieved_at`

### evidence_units

`evidence_id, doc_id, feature_id, claim_no, task_role, location_type, locator, excerpt_or_paraphrase, evidence_mode, disclosure, relation_fit, date_eligible, officially_verified, confidence, reviewer, reviewed_at`

`evidence_mode`：`text_explicit|figure_explicit|text_figure_combined|implicit_with_reason|model_inference_only`。模型推断永远不能伪装成原文明确公开。

### feature_maps

`map_id, target_id, doc_id, feature_id, right_instance_id, right_country, operative_claim, coverage, evidence_ids[], missing_reason, single_document_complete, combination_group, technical_effect, teaching_or_motivation, task_specific_finding`

FTO 中 `right_instance_id + operative_claim` 是风险映射的必填联合定位；不能只把同族层面的 `doc_id` 浮动复用于多个国家。

### legal_status_checks

`status_id, right_instance_id, doc_id, national_right_identifier, right_country, office, official_register_url, checked_at, application_or_patent_status, operative_claim_version, active_claims[], grant_or_expiry_event, lapse_or_limitation_event, uncertainty`

`right_instance_id` 唯一表示一个国家中的具体权利实例。国家文献只能对应本国；EP 文献可对应 EPC 实施国，但必须另给该国 `national_right_identifier` 和官方登记簿证据。`active_claims` 必须逐项列为数组，便于 FTO 映射精确引用。

### oa_objections

`objection_id, office, oa_date, deadline, legal_basis, affected_claims, examiner_document, examiner_locator, examiner_reasoning, applicant_position, proposed_amendment, support_locator, added_matter_check, recommended_action`

### limitations_and_audit

局限：`limitation_id, category, description, impact, mitigation`。

审计事件：`event_id, timestamp, action, actor, input_hash, output_hash, credits, elapsed_seconds`。

## 校验硬门

工作中使用 `validate-evidence --stage draft` 检查结构和引用；交付必须使用默认的 `--stage final`。空骨架只允许通过 draft，绝不能通过 final。

1. 任一 `coverage=covered` 必须至少关联一个存在的 `evidence_id`。
2. 新颖性单篇完整披露必须由一个 `doc_id` 覆盖全部必要特征，并满足关键日。
3. FTO 每个实际权利国家都必须存在法域相容的权利实例、官方状态记录、有效权项版本和核验日期；`EP` 不是实际权利国家。每条映射必须绑定 `right_instance_id + right_country + operative_claim`，且该权项必须存在于该实例的 `active_claims[]`；每个候选权利实例对每个 `necessary=true` 产品特征都必须有映射，即使结论是 `coverage=missing` 也要记录理由；覆盖/风险判断不得只由 `model_inference_only` 支持。
4. OA 正式修改建议必须有 `support_locator`。
5. 无效/公众意见证据必须有公开日、适格性和定位。
6. 竞品统计必须披露同族去重、申请人归一化、截断和分母。
7. `feature_maps` 的 target/doc/feature/evidence 必须全部存在并相互一致；所有 ID 必须唯一。
8. 已执行的 `search_runs.query_hash` 必须在权威 `case.json.route_lock.queries` 中有一致的 engine、paid_command、market、round、状态、结果数和积分；全部预留记录均须完成并进入 `search_runs`。
