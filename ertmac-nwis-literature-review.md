# eRTMAC-NWIS Literature and Prior-Art Review

**Project:** *eRTMAC-NWIS (Nearby Wells Intelligence System): An AI-Powered Offset Well Knowledge and Decision Support Platform for Drilling Operations*  
**Evidence cutoff:** 28 September 2026

The strongest defensible conclusion is that nearly every individual NWIS capability already exists somewhere in research, commercial software, or patents—but a transparently validated, formation- and depth-aware platform combining offset-well ranking, document extraction, live drilling analytics, event prediction, geospatial visualization, and provenance-grounded natural-language access is not well documented as one integrated public system.

A broad novelty claim such as “the first AI system using nearby wells for drilling decisions” would be unsafe. A stronger project contribution is an **explainable, multimodal offset-well intelligence workflow** that integrates these functions and demonstrates cross-well validation on public data before deployment with Oil India Limited data.

## A. Executive Summary

The technical foundation for NWIS is well established:

- Offset-well ranking can combine geological, spatial, trajectory and risk similarity. Landmark’s patent family explicitly covers automated ranking across multiple data sources, including risks inferred through NLP, while another patent family selects offsets using segmented well-trajectory similarity. [Automated Offset Well Analysis](https://patents.google.com/patent/WO2021040780A1/en) [Trajectory Similarity Patent](https://patents.google.com/patent/US20240151134A1/en)
- Daily drilling and mud-report text can be converted into event labels such as losses, influx and stuck pipe. Research has progressed from sentence classification into EVENT, SYMPTOM and ACTION classes to LLM-, RAG- and fine-tuning-based extraction. [Event Detection in Drilling Remarks](https://onepetro.org/SPEDC/proceedings-abstract/22DC/2-22DC/482139)
- Real-time prediction has been demonstrated for lost circulation, stuck pipe, stick-slip, pore pressure and activity segmentation, but most studies use proprietary, single-field or small datasets and rarely prove transfer to unseen fields.
- Public data are fragmented. Volve is the closest complete reference because it combines WITSML drilling streams, reports, logs, seismic, geological models and production data, while Diskos, NLOG, UK NDR, Utah FORGE and geological-survey repositories can supplement trajectories, reports, coordinates and logs.
- Recent work is moving toward multimodal models, RAG and foundation models. DriMM aligns sensor time series with DDR activity text, but a 2025 drilling benchmark found that compact CNNs often matched or exceeded time-series foundation models and that generic pretraining offered limited or negative benefit. [DriMM](https://openreview.net/pdf?id=NlOwF1b84H) [Time-Series Foundation Model Study](https://openreview.net/forum?id=LcAZkhb9uz)
- Commercial products provide strong real-time monitoring, digital twins and predictive analytics, but public descriptions rarely establish transparent offset selection, report-level evidence retrieval, model evaluation or public APIs.

The recommended research prototype should prioritize:

1. A reproducible offset-ranking model with interpretable component scores.
2. A depth- and formation-indexed drilling-event knowledge base.
3. OCR and schema-constrained extraction from WCRs and DDRs.
4. Hybrid keyword, vector and knowledge-graph retrieval with source-page citations.
5. One or two well-supported risk models—not an unvalidated model for every possible drilling hazard.
6. Real-time alerts generated from both historical offset events and live anomaly models.
7. Evaluation by leave-one-well-out and leave-one-field-out testing.

## B. State of the Art

| Technology | Applied to drilling/oil and gas? | Evidence level | NWIS implication |
|---|---|---|---|
| Random forest, XGBoost, AdaBoost | Yes; extensively applied to mud loss, stuck pipe and drilling classification | Mature research, some field deployment | Essential baselines; often more defensible than deep models |
| LSTM/GRU | Yes; kick, loss, drilling-state and anomaly applications | Established, but frequently small or simulated datasets | Useful where temporal sequence genuinely matters |
| 1D CNN/TCN | Yes; drilling-event segmentation and real-time classification | Strong emerging evidence | Good low-latency baseline for live streams |
| Transformers | Applied recently to stuck-pipe precursors and drilling-language tasks | Emerging | Promising, but require careful cross-well validation |
| Time-series foundation models | Benchmarked directly on drilling in 2025 | Experimental | Do not assume superiority over CNNs |
| Multimodal time series and text | DriMM demonstrated joint representations and cross-modal retrieval | Research prototype/workshop evidence | Highly relevant to linking live traces with historical DDR descriptions |
| LLM + RAG | Applied to E&P knowledge and drilling-risk extraction | Emerging conference/industrial research | Suitable for evidence retrieval and explanation, not primary safety control |
| Agentic AI | Demonstrated in industrial pilots, conference work and public challenges | Early-stage | Use only through constrained tools and approval gates |
| Knowledge graphs | Applied in petroleum-domain and industrial knowledge systems | Emerging | Useful for explicit well–formation–event–action relationships |
| OCR and layout-aware AI | Technically mature in document AI; petroleum-specific evaluations remain sparse | Mixed | Necessary for scanned WCRs, but must preserve page provenance |
| Digital twins | Applied to drilling and well construction | Commercially important | Suitable for live state estimation and scenario analysis |
| Physics-informed ML | Applied to ROP, pressure and drilling digital twins | Emerging | Preferable when predictions must respect hydraulics or mechanical constraints |
| GNNs | Direct offset-drilling validation remains limited | Mostly proposed for NWIS-type use | Treat as a research extension, not the initial production model |
| Explainable/probabilistic ML | Demonstrated through mixture-density mud-loss models and hybrid physical models | Emerging | Important for calibrated risk intervals and operator trust |

The clearest recent warning is that architectural novelty is not equivalent to operational value. In a 2025 industrial drilling benchmark, fully convolutional networks often matched or outperformed time-series foundation models, while generic pretraining sometimes reduced segmentation performance. [Study](https://openreview.net/forum?id=LcAZkhb9uz)

## C. Existing Academic Research

Academic work relevant to NWIS falls into six connected streams:

- **Drilling-event prediction:** lost circulation, stuck pipe, kick/influx, stick-slip, pore pressure and NPT.
- **Operational-state recognition:** converting sensor streams into drilling activities and states.
- **Report mining:** extracting events, symptoms, actions and NPT information from free text.
- **Offset and analog selection:** ranking wells through spatial, geological, trajectory or production similarity.
- **Digital twins and hybrid models:** combining physical equations with live data and learned residuals.
- **Knowledge access:** semantic retrieval, knowledge graphs, RAG and engineering assistants.

The literature is usually vertically specialized. A mud-loss paper predicts one event from one field; a report-mining paper extracts event classes; an offset-selection patent ranks candidate wells; and a commercial platform monitors live operations. Very few public studies evaluate the complete chain from document ingestion to a real-time, provenance-bearing recommendation.

## D. Latest Research — 2024–2026

| Work | Problem and data | Method and training | Results | Limits and availability | NWIS contribution |
|---|---|---|---|---|---|
| **Retrieving Operation Insights with GenAI LLM** (2024) | Extract drilling risks from DDRs for offset-well planning; well and sample counts not publicly reported | Prompt optimization, RAG, Llama 2/3, Mistral and GPT-3.5 fine-tuning | Prompt/RAG reportedly reached 80–85% accuracy and over 70% precision/recall; fine-tuned models exceeded 90% accuracy and 80% precision/recall | Conference paper; proprietary dataset; code/data not reported public | Direct support for DDR risk extraction and offset-well retrieval. [Source](https://onepetro.org/SPEADIP/proceedings-abstract/24ADIP/24ADIP/585552) |
| **EPChat, SPE 220833-MS** (2024) | E&P-domain question answering; dataset size not reported publicly | Domain fine-tuning plus RAG | Reported reduction in hallucination and improved contextual relevance | Conference paper; data/code availability not reported | Supports an evidence-grounded petroleum assistant. [Source](https://onepetro.org/SPEATCE/proceedings-abstract/24ATCE/24ATCE/563645) |
| **Mud Loss Prediction using seismic attributes** (2024) | Pre-drill prediction from 15 wells and 16 seismic attributes | Mixture Density Network; 80:20 split | Training/test mean relative error 6.9%/7.5%; R² 0.90/0.88 | One oilfield; public-data status unclear | Strong precedent for uncertainty-aware formation-scale risk maps. [DOI](https://doi.org/10.1016/j.petsci.2023.10.024) |
| **Boosting for Mud Loss, SPE 221583-MS** (2024) | Over 7,000 records and 27 features from Utah FORGE well MXY | AdaBoost, LightGBM, XGBoost and random forest | XGBoost R² 0.935; RF R² 0.934 | One well; random row splitting may overestimate performance | Reproducible NWIS prototype task using public drilling data. |
| **Physics-Informed AI Digital Twin** (2024) | Optimize ROP/MSE and reduce shocks using a small offset set | Physics-based time-domain model plus ML at the edge | Reported 40% average drilling-performance improvement | Exact model, sample size and code undisclosed | Supports a hybrid real-time twin. [Source](https://onepetro.org/SPEADIP/proceedings-abstract/24ADIP/24ADIP/585182) |
| **DriMM** (2025) | Joint representation of drilling sensors and DDR activity text | Time-series encoder plus pretrained language model with contrastive alignment | Enabled cross-modal retrieval and zero-shot activity classification | Workshop paper; public dataset/deployment not established | Direct basis for matching live patterns with historical descriptions. [Paper](https://openreview.net/pdf?id=NlOwF1b84H) |
| **Foundation Models for Drilling Segmentation** (2025) | Drilling-state segmentation | Pretrained/from-scratch time-series foundation models compared with FCNN | CNNs often matched or exceeded foundation models; pretraining could hurt | Workshop evidence, not safety validation | Mandates a simple-CNN baseline. [Paper](https://openreview.net/pdf?id=LcAZkhb9uz) |
| **Lost Circulation Intensity from Well Logs** (2025) | Six-class loss intensity using well logs | Multiple classifiers | Evaluated with accuracy, precision, recall, F1, MCC and kappa | Proprietary field data; wells not reported in retrieved metadata | Formation/log-based hazard priors. [Source](https://www.cell.com/heliyon/fulltext/S2405-8440(24)17090-9) |
| **Transformer Stuck-Pipe Prediction** (2026) | Stuck-pipe precursor detection in continuous data | End-to-end Transformer on 5,000 samples | 94.5% accuracy; reported warning 1.5–2 hours ahead | Wells, balance and independent-field validation not reported | Relevant to live early warning, subject to strict replication |
| **Hybrid Pore-Pressure/Fracture-Gradient Model** (2026) | Offshore carbonate pressure and fracture-gradient prediction | Empirical methods, field calibration and ML correction | Reported improvement over classical estimates | Field-specific | Supports physics-constrained mud-window estimation |
| **Masked-Autoencoder Foundation Models Mapping Study** (2026) | Downhole metric prediction from surface data | Review of 13 papers from 2015–2025 | Found ANN/LSTM dominance and no direct MAE validation | Preprint proposing rather than validating MAEs | Identifies self-supervised cross-well pretraining as an open experiment. [Source](https://arxiv.org/abs/2604.15169) |

### Interpretation

- **Actually applied:** transformers, multimodal contrastive learning, LLM/RAG, CNNs, LSTM/GRU, hybrid physics–ML, probabilistic mixture-density networks and digital twins.
- **Applied but not yet proven superior:** time-series foundation models.
- **Mostly exploratory for NWIS:** GNN-based multiwell risk propagation and fully autonomous engineering agents.
- **Commercially advertised but incompletely disclosed:** agentic recommendations, proprietary foundation models and integrated AI copilots.

## E. Existing Datasets

| Dataset | Source/year | Wells/records | Relevant contents | Labels | Format/access | NWIS relevance |
|---|---|---:|---|---|---|---|
| **Volve Field dataset** | Equinor, 2018 | Approximately 40,000 files; exact well count varies by subset | WITSML streams, reports, logs, seismic, models, completions and production | Some activity information; event labels require extraction | Public; WITSML, PDF, TIFF, LAS, DLIS, SEG-Y | Best single public multimodal source |
| **Volve DDR Alpaca** | Hugging Face, 2024 | 1,759 DDR files; 1,596 train, 163 test | DDR text converted from WITSML | Text summarization pairs | Public Hugging Face | Fast report-summarization starting point. [Dataset](https://huggingface.co/datasets/bengsoon/volve_alpaca) |
| **Volve preprocessed drilling** | GitHub | Not reported | WITSML converted to CSV with code | Not reported | Public code | Useful for stream prototyping. [Repository](https://github.com/f0nzie/volve-drilling) |
| **Diskos Well Database** | Norwegian Offshore Directorate | Not reported | Drilling reports, mud logs, stratigraphy, pressure, logs and surveys | Mostly unlabelled | Released data public; some restricted | Excellent multiwell document, trajectory and formation source. [Dataset](https://www.sodir.no/en/diskos/wells/) |
| **NLOG boreholes** | Netherlands | Not reported | Coordinates, reports, logs, lithostratigraphy and deviation surveys | Mostly unlabelled | Public after confidentiality; PDF/TIFF/LAS/LIS | Strong for spatial discovery and OCR. [Dataset](https://www.nlog.nl/en/boreholes) |
| **UK NSTA NDR/Open Data** | UK regulator | Not reported | Wells, completion reports, logs, operational/geological data and GIS | Mostly unlabelled | Public/released data | Strong for maps, WCR extraction and formation correlation |
| **Utah FORGE 58-32** | US DOE/GDR | One principal well in cited packages; record count not reported | Pason data, logs, testing and core | Labels vary by package | Public | Best simple drilling-parameter benchmark. [Dataset](https://catalog.data.gov/dataset/utah-forge-drilling-data-for-student-competition-4791b) |
| **Pressure/kick dataset** | 2024 research | More than 2,000 samples; 28 variables; simulated | Drilling variables | Pressure and kick labels | Availability claimed; repository must be verified | Useful for software validation, not field proof |
| **Azadegan loss dataset** | 2021/22 study | 20 wells; 65,376 records; 17 variables | Operational and mud variables | Five loss classes | Availability not reported | Strong class-imbalance case study. [Paper](https://link.springer.com/article/10.1007/s13202-021-01411-y) |
| **Southern Iran loss dataset** | Zenodo, 2024 | Two wells; 1,003 samples | Mud and formation variables | Loss target | Public | Small reproducible regression set. [Dataset](https://zenodo.org/records/21725554) |
| **H-field seismic mud-loss set** | 2024 | 15 wells; records not reported | Sixteen seismic attributes | Loss rate per footage | Public status not reported | Pre-drill geological risk |
| **USGS Texas scanned logs** | USGS, 2026 update | More than 15,000 historical logs | Scanned historical well/geophysical logs | None | Public PDFs/TIFF | OCR/layout benchmark. [Dataset](https://data.usgs.gov/datacatalog/data/USGS:64da9e5fd34ef477cf3ee769) |
| **Kansas digital logs** | KGS | 21,780 LAS files reported for end-2024 | Locations, completions, formation tops and logs | Mostly unlabelled | Public search/download | Large-scale location and log testing. [Dataset](https://www.kgs.ku.edu/Magellan/Logs/) |
| **OSDU schemas/test data** | OSDU Forum | Not reported | Well master, logs, trajectories and reference schemas | N/A | Open schemas/test data | Canonical data model rather than training corpus. [Documentation](https://osduforum.org/osdu-data-definition-documentation/) |

No verified public dataset contains, at commercial-field scale, synchronized live channels, trajectories, formations, DDR/WCR narratives, losses, kicks, stuck pipe, cementing failures, NPT causes and mitigation outcomes. NWIS therefore requires **dataset composition**, not selection of one perfect dataset.

## F. Datasets Used in Recent Papers

| Paper/problem | Exact dataset used | Availability |
|---|---|---|
| Lost-circulation class prediction | 65,376 records, 17 variables, 20 Azadegan wells | Not reported public; likely operator data |
| Carbonate mud-loss prediction | Sixteen seismic attributes around 15 H-oilfield wells | Not reported public |
| Boosting mud-loss prediction | More than 7,000 points, 27 features, Utah FORGE well MXY | Underlying FORGE data public; processed table may need reconstruction |
| Hybrid optimized MLP loss prediction | 1,003 points from two southern Iranian wells | Public through Zenodo |
| Stuck-pipe probability | DDR-derived data from 85 Middle Eastern wells | Not reported public |
| Stuck-pipe remediation | Drilling, formation and mud data from 385 southern Iraqi wells | Not reported public |
| Stuck-pipe Transformer | 5,000 field samples | Wells and public status not reported |
| Early pack-off detection | Test data included 18 cases across five wells | Proprietary industrial data |
| Kick detection | Dynamic simulations rather than field events | Academic dataset availability must be checked |
| Analog-well clustering | Production profiles from 100 Barnett shale gas wells | Public status not reported |
| DDR event retrieval with LLMs | Proprietary DDR benchmark; size not disclosed | Restricted/not reported |
| DriMM | Sensor time series paired with DDR activity labels | Public status not established |

## G. Commercial and Industrial Systems

| Platform | Verified functions | Offset/document/map evidence | Unclear or proprietary |
|---|---|---|---|
| **SLB DrillOps** | Advisory or automated well execution, reporting, real-time decision support, multiwell monitoring and predictive alarms | Multiwell monitoring explicit; transparent offset similarity and OCR/RAG not established publicly | Architectures, datasets, thresholds, calibration and independent accuracy. [Official page](https://www.slb.com/products-and-services/delivering-digital-at-scale/drilling/drilling-operations) |
| **Halliburton DecisionSpace 365 Well Construction** | Planning-to-operations workflows, digital twins, cloud deployment and AI/ML automation | Well-data integration explicit; natural-language WCR/DDR evidence retrieval not verified | Offset-ranking details and model performance. [Official page](https://www.halliburton.com/en/software/decisionspace-365-enterprise/decisionspace-365-well-construction) |
| **Baker Hughes Leucipa** | AI automation, real-time integration, predictive analytics and GenAI assistant | Primarily production rather than drilling | Direct applicability to offset-well drilling analysis. [Official page](https://www.bakerhughes.com/oilfield-services-and-equipment-digital/leucipa-automated-field-production-solution) |
| **Weatherford Centro/Victus/Vero** | Integrated well construction, remote delivery and automation | Integrated execution is documented | Algorithms, data volumes and evaluation methodology |
| **Oil India digital initiatives** | Public reporting indicates AI use for reservoir modelling, drilling optimization and predictive maintenance | No public technical evidence found for a full NWIS implementation | eRTMAC architecture, report indexing, offset ranking and model details |

Commercial descriptions should be treated as capability statements, not independent validation. Terms such as “AI-powered,” “digital twin” and “predictive” do not reveal unseen-well performance, false-alert controls or recommendation provenance.

## H. Patent Prior Art

This is a prior-art landscape, not a novelty, validity or freedom-to-operate opinion.

| Patent | Date/assignee | Core concept | Similarity to NWIS | Difference |
|---|---|---|---|---|
| **Automated Offset Well Analysis**, WO2021040780A1 / US20220307366A1 | Filed 2020; Landmark Graphics Corporation on US member | Aggregates disparate data, calculates similarity features, ranks offsets and includes NLP-derived risks | Very close to offset ranking, aggregation and textual-risk analysis | NWIS adds live monitoring, depth alerts, map workflow and document RAG. [Patent](https://patents.google.com/patent/WO2021040780A1/en) |
| **Offset Well Analysis Using Well Trajectory Similarity**, US20240151134A1 / US12270292B2 | Published 2024; grant 2025 | Segments trajectories, computes similarity and selects offsets | Directly relevant to trajectory selection | Does not establish the complete OCR, event-KG and live retrieval stack. [Patent](https://patents.google.com/patent/US20240151134A1/en) |
| **Automated Offset Well Analysis**, US20220026596A1 / US11747502B2 | Published 2022; granted 2023 | Trains ML on offset data to generate drilling-risk profiles and adjust parameters | Direct overlap with offset-based prediction and recommendations | NWIS can emphasize formation-aware evidence, uncertainty and human approval. [Patent](https://patents.google.com/patent/US20220026596A1/en) |

Automated offset ranking and offset-trained risk prediction should not be presented as standalone inventions. The defensible emphasis is integration research, evaluation, explainability, multimodal evidence alignment and safe eRTMAC integration.

## I. Offset/Analog Well Intelligence

A similar well should not be defined merely by geographic proximity. A technically defensible score is:

\[
S(i,q)=w_sS_{spatial}+w_gS_{geology}+w_fS_{formation}+w_tS_{trajectory}+w_dS_{design}+w_oS_{operations}+w_eS_{events}
\]

Weights should vary by use case. Casing design may prioritize pressure and formations; stuck-pipe retrieval may prioritize trajectory, hole section, mud, lithology and torque/drag behavior.

| Dimension | Possible measure | Role |
|---|---|---|
| Geographic proximity | Surface or minimum 3D wellbore distance | Candidate-generation filter, not final similarity |
| Formation sequence | Ordered overlap, top-depth offset, lithology similarity | Primary geological context |
| Depth | MD, TVD/TVDSS and distance from formation boundaries | Aligns events across structurally displaced wells |
| Trajectory | Segment-wise 3D distance, dogleg and inclination/azimuth profile | Important for torque, drag and hole cleaning |
| Hole/casing design | Hole size, casing depth, BHA and mud program | Operational comparability |
| Time-series behavior | DTW or learned sequence embeddings | Finds similar operational signatures |
| Event history | Weighted overlap of event types, causes and severity | Supports risk transfer |
| Textual experience | Lexical and dense similarity | Retrieves mitigations and lessons |

A recommended ranking workflow is:

1. Apply hard spatial and basin/field filters.
2. Compare formation sequences and pressure regimes.
3. Calculate trajectory similarity over the upcoming section.
4. Compare design, hole section, mud and BHA attributes.
5. Align depth-indexed streams using formation-relative depth and constrained DTW.
6. Compare event and mitigation histories.
7. Return component scores and explanations.
8. Re-rank dynamically as the current well state becomes known.

## J. NLP, OCR, LLM and RAG

| Approach | Strength | Weakness | NWIS role |
|---|---|---|---|
| Dictionaries/regex | Precise for units, depths, dates and known terms | Poor handling of variation | First-pass extraction and validation |
| Traditional classifiers | Cheap and interpretable | Limited context and transfer | Event/sentence baseline |
| NER/relation extraction | Produces structured entities and links | Requires annotation and ontology | Extract event, formation, cause and action |
| BERT/PetroBERT | Contextual classification and NER | Domain/language and sequence limits | Fine-tuned report classifier |
| Layout-aware models | Understand tables, sections and page coordinates | Annotation and OCR cost | WCR/DDR forms and tables |
| LLM extraction | Flexible schema filling | Hallucination and nondeterminism | Constrained extraction with validation |
| Hybrid RAG | Evidence-backed question answering | Retrieval errors propagate | Engineer Q&A with page citations |
| Knowledge graph | Explicit relationships and traversal | Ontology/entity-resolution effort | Well–formation–event–action graph |
| Multimodal VLM | Handles scans, tables, figures and text | Privacy, cost and evaluation challenges | Difficult-page exception handling |

### Event schema

Each extracted record should contain:

- `well_id`
- `report_id`
- `page_or_section`
- `event_type`
- `start_time`, `end_time`
- `md_from`, `md_to`, `tvd_from`, `tvd_to`
- `formation`
- `hole_section`
- `operation`
- `symptoms`
- `cause`
- `consequence`
- `action_taken`
- `outcome`
- `npt_hours`
- `severity`
- `extraction_confidence`
- `human_validation_status`
- `source_text_span`
- `source_page_image`

### Retrieval architecture

- SQL/PostGIS for well radius, formation and depth filters.
- BM25 for exact terminology, equipment and abbreviations.
- Dense vectors for paraphrased events and mitigation narratives.
- Knowledge-graph traversal for causes, actions, equipment and formations.
- Time-series similarity for matching live patterns.
- Reranking constrained by offset score and current-well context.
- LLM synthesis only after retrieval, with each answer tied to a well, depth, date and source page.

The system should respond “no supported evidence found” rather than infer missing operational facts.

## K. AI/ML Drilling-Risk Prediction

| Problem | Candidate data | Inputs | Target | Suitable models | Evaluation |
|---|---|---|---|---|---|
| Mud loss | FORGE, Azadegan study design, public Iran set, OIL data | Flow difference, pit volume, SPP, ROP, WOB, RPM, mud density, formation | Occurrence, severity or rate | RF/XGBoost; ordinal classifier; TCN; MDN | PR-AUC, event F1, false alarms/hour, lead time, calibration |
| Kick/influx | Digital-twin data plus field replay | Flow imbalance, pit gain, SPP, return flow, gas, pump rate | Probability and influx size | Physics residual, TCN/LSTM, boosting | Event recall, false-alarm rate, detection time, size MAE |
| Stuck pipe | Literature designs, DDR labels, OIL data | Torque, hookload, SPP, ROP, depth, overpull, mud properties | Stuck/pack-off warning | XGBoost, HMM, TCN/1D CNN; Transformer with enough data | Precision, recall, lead time, held-out wells |
| NPT | DDR/WCR narratives and activity states | Operation sequence, equipment, formation, event text | Category, duration, root cause | Text classifier plus survival/regression model | Macro-F1, duration MAE, calibration |
| Torque anomaly | WITSML | Torque, RPM, WOB, hookload, flow, SPP, depth and trajectory | Anomaly/dysfunction state | Physics residual, change point, autoencoder, TCN | Detection delay, false alarms/hour |
| Overpressure | Logs, tests and seismic | Sonic, density, resistivity, GR, depth, lithology, seismic | Pore pressure/fracture gradient | Physics model plus ML residual | RMSE, MAE, interval coverage |
| Cementing risk | WCRs, cement reports and OIL jobs | Caliper, losses, mud, design, temperature and pressure | Poor placement/integrity issue | Rules/Bayesian model initially; boosted trees later | Recall, calibration, false alarms/job |
| Formation classification | LAS/DLIS and mud logs | GR, resistivity, density, neutron, sonic, ROP, cuttings | Formation/lithology | XGBoost, 1D CNN, HMM/CRF | Macro-F1, boundary-depth error |
| Offset similarity | Volve, Diskos, NLOG, OIL wells | Location, formations, trajectory, design and events | Ranked wells | Multi-view distance, DTW, metric learning, learning-to-rank | Precision@k, NDCG, engineer agreement |
| Event retrieval | DDR/WCR corpora | Query, metadata, entities and embeddings | Relevant events/passages | BM25 + vectors + reranker + graph | Recall@k, MRR, grounded accuracy |
| Document extraction | Volve/NSTA/NLOG reports | OCR, layout and page images | Structured event schema | Rules + layout model + constrained LLM | Field exact match, entity/relation F1 |
| Risk recommendation | Validated cases and procedures | Current context, risk and historical outcomes | Ranked mitigations | Case-based reasoning, rules and grounded RAG | Expert acceptance and contraindication rate |

### Validation requirements

- Leave-one-well-out tests.
- Leave-one-field-out tests where possible.
- Performance by formation and hole section.
- Event-level, not only sample-level, precision and recall.
- False alarms per drilling hour.
- Median warning lead time.
- Calibration/reliability analysis.
- Separate reporting for rare severe events.
- Robustness to missing, delayed and noisy channels.
- Baselines using rules, RF/XGBoost and compact CNN/TCN models.

## L. Research Gap

### What already exists

- Automated offset-well ranking over heterogeneous data.
- Trajectory-based offset selection.
- Offset-trained drilling-risk prediction.
- DDR event extraction for losses, influx and stuck pipe.
- LLM/RAG retrieval of drilling risks from offset reports.
- Multimodal alignment of drilling sensors and text.
- Real-time multiwell monitoring and drilling advisory products.
- Digital-twin drilling optimization.

### What remains inadequately demonstrated

No well-documented public system was identified that combines and validates all of the following:

1. Geospatial candidate discovery.
2. Explainable multi-criteria offset ranking.
3. OCR of WCRs and DDRs.
4. Event, cause, action and outcome extraction.
5. Formation-relative and depth-normalized correlation.
6. Live stream alignment with historical offsets.
7. Calibrated predictive risk.
8. Evidence-bearing proactive alerts.
9. RAG linked to exact pages and sensor intervals.
10. Map and engineering dashboard.
11. Cross-well and cross-field validation.
12. Human feedback and model governance.

The gap is therefore **integration plus trustworthy validation**, not invention of an individual model.

### Defensible contribution

> A formation- and trajectory-aware multimodal retrieval and early-warning framework that aligns real-time drilling streams with structured events extracted from historical offset-well documents, ranks evidence by explainable well similarity, and generates provenance-linked recommendations under calibrated uncertainty.

Potential sub-contributions include:

- A labelled DDR/WCR event ontology and annotation protocol.
- A benchmark for formation-relative cross-well event retrieval.
- A multi-view similarity model evaluated against engineer rankings.
- Hybrid sensor–text retrieval comparing DTW, CNN embeddings and multimodal contrastive learning.
- A source-grounded RAG evaluation dataset.
- A lead-time-aware alert evaluation framework.
- Human-in-the-loop measurement of event corrections and recommendation acceptance.

## M. Potential Contribution of NWIS

### Minimum viable research system

- Offset-well map and similarity ranking.
- OCR/document ingestion.
- Event extraction for mud loss, influx/kick, stuck pipe and NPT.
- Formation/depth correlation view.
- Hybrid historical-event search.
- One live anomaly model, preferably mud loss or stuck pipe.
- A depth-ahead alert citing the relevant offset and report page.
- A RAG interface restricted to retrieved evidence.
- Expert feedback and audit logging.

### Success criteria

- High top-k recall of relevant offset events.
- Accurate extraction of event, depth, formation and mitigation.
- Lower engineer search time than manual report review.
- Ranking agreement with drilling engineers.
- Useful lead time with controlled false alarms.
- Stable held-out-well performance.
- No unsupported operational recommendations in the evaluated test set.

## N. Recommended Dataset Strategy

| Required data | Publicly available? | Example | Available features | Major gaps |
|---|---|---|---|---|
| Well location | Yes | Diskos, NLOG, NSTA, KGS | Coordinates, IDs and status | CRS and quality normalization |
| Well trajectory | Yes | Diskos, NLOG, Volve | MD, inclination, azimuth and path | Incomplete surveys |
| Historical drilling parameters | Limited | Volve, FORGE | WITSML/Pason channels, depth and time | Few fields; inconsistent labels |
| Formation/depth | Yes | Volve, Diskos, NLOG, KGS | Tops, lithostratigraphy and logs | Naming and datum differences |
| Mud losses | Partly | FORGE studies, research datasets, DDRs | Loss rate/classes or text events | Few open field-validated labels |
| Kicks | Limited | Digital-twin dataset | Twenty-eight variables and target | Simulated rather than field events |
| Stuck pipe | Rarely | Literature and extracted DDR labels | Parameters and event records | Raw data mostly proprietary |
| NPT | Partly | Volve DDRs | Text and operation timelines | Root-cause labels require annotation |
| Cementing events | Reports exist | Diskos, NSTA, Volve | Descriptions and job information | Outcome labels sparse |
| Drilling reports | Yes | Volve, Diskos, NLOG, NSTA | PDF, TIFF and WITSML reports | OCR and licensing variation |
| Lessons learned | Rarely structured | DDR/WCR narratives | Actions/outcomes extractable | No standard public ontology |
| Real-time data | Limited | Volve, FORGE | Sensor streams | Historical replay rather than live rig |

### Public-data prototype

1. Use **Volve** as the multimodal backbone.
2. Use **Volve DDR Alpaca** for initial text experiments, but evaluate against original reports.
3. Use **Utah FORGE** for reproducible drilling analytics and mud-loss studies.
4. Use the pressure/kick digital-twin data only for software validation and label it simulated.
5. Add **NLOG or Diskos** wells for documents, trajectories and geological diversity.
6. Use **USGS/KGS** reports and logs for OCR and metadata scaling, not field-risk claims.
7. Use **OSDU-compatible schemas** for identifiers and integration.

Authentic historical records can be replayed chronologically to emulate streaming without fabricating measurements.

## O. Recommended Technical Architecture

### Data layer

- Object storage for WCRs, DDRs, LAS/DLIS, WITSML and images.
- Relational store for wells, wellbores, reports, formations, casing and BHA.
- PostGIS for locations, trajectories and spatial search.
- Time-series database for time/depth-indexed channels.
- Graph database for well–formation–interval–event–cause–action–equipment relations.
- Vector index for report passages, event summaries and time-series embeddings.
- OSDU-compatible identifiers and units where practical.

### Processing layer

1. Register files and calculate checksums.
2. Detect born-digital versus scanned documents.
3. Apply OCR where required.
4. Reconstruct reading order, tables and sections.
5. Normalize units, dates, well names and depth references.
6. Extract entities, relations and event frames.
7. Link each field to source page and bounding box.
8. Resolve formation names against a controlled dictionary.
9. Align time, MD, TVD/TVDSS and formation-relative depth.
10. Validate with deterministic rules and human review.

### Intelligence layer

- Offset candidate generation.
- Explainable multi-view similarity.
- Formation/depth correlation.
- SQL + BM25 + dense vector + graph retrieval.
- Calibrated risk models.
- Physics residual and temporal anomaly detection.
- RAG with constrained evidence synthesis.
- Case-based recommendations from prior actions and outcomes.
- Confidence intervals, missing-data and out-of-distribution checks.

### Real-time layer

- Ingest WITSML/eRTMAC streams.
- Validate range, units, freshness and missingness.
- Infer drilling state and rolling features.
- Project the current trajectory into upcoming formations.
- Retrieve events from similar offsets in an upcoming depth window.
- Run anomaly and risk models.
- Merge signals through explicit rules or calibrated ensembles.
- Issue advisory alerts with risk, lead distance/time, confidence and source evidence.
- Require operator acknowledgement and preserve the advisory role unless separately safety-certified.

### Application layer

- Active-well and offset-well map.
- Similarity explanation panel.
- Formation/trajectory correlation view.
- Multiwell depth tracks.
- Historical event timeline.
- Alert queue with severity and lead time.
- Document viewer opening at cited pages.
- Natural-language query interface.
- Expert correction interface.
- Full audit trail.

### Example query

For “Which nearby wells experienced mud losses in this formation?” NWIS should:

1. Resolve the current formation and uncertainty.
2. Query PostGIS for candidate wells.
3. Rank candidates by formation, trajectory, design and operational context.
4. Query the event graph for mud losses in equivalent intervals.
5. Retrieve original report passages and sensor windows.
6. Return wells, depths, severity, mitigation and outcome with citations.
7. Separate extracted facts from predicted risk.

## P. Top 20 Papers to Read

1. **“Retrieving Operation Insights with GenAI LLM: Comparative Analysis and Workflow Enhancement.”** SPE conference paper, 2024. Directly addresses LLM/RAG extraction of offset-well risks from DDRs. [Link](https://onepetro.org/SPEADIP/proceedings-abstract/24ADIP/24ADIP/585552)
2. **“Preliminary Research on Applications of Large Language Models in E&P Industry.”** SPE 220833-MS, 2024. DOI: [10.2118/220833-MS](https://doi.org/10.2118/220833-MS).
3. **Buiting et al. “DriMM: Drilling Multimodal Model for Time-Series and Text in the Era of Large Models.”** ICML FMSD Workshop, 2025. [Paper](https://openreview.net/pdf?id=NlOwF1b84H)
4. **Khaouja et al. “Do Large Foundation Models Improve Time Series Segmentation? An Industrial Case Study in Oil and Gas Drilling.”** ICML FMSD Workshop, 2025. [Paper](https://openreview.net/pdf?id=LcAZkhb9uz)
5. **Pang et al. “Machine Learning for Carbonate Formation Drilling: Mud Loss Prediction Using Seismic Attributes and Mud Loss Records.”** *Petroleum Science*, 2024. DOI: [10.1016/j.petsci.2023.10.024](https://doi.org/10.1016/j.petsci.2023.10.024).
6. **Wood, Mardanirad and Zakeri. “Effective Prediction of Lost Circulation from Multiple Drilling Variables.”** *Journal of Petroleum Exploration and Production Technology*, 2021/2022. [Paper](https://link.springer.com/article/10.1007/s13202-021-01411-y)
7. **Okai et al. “Application of Boosting Machine Learning for Mud Loss Prediction During Drilling Operations.”** SPE 221583-MS, 2024.
8. **“Digital Twins Revolutionizing Oil and Gas Industry: Optimizing Drilling Operations with Physics Informed AI.”** SPE conference paper, 2024.
9. **“Hybrid Physics-Machine Learning Models for Predicting Rate of Penetration.”** *Scientific Reports*, 2024. [Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10933403/)
10. **“Data-Driven Indicators for the Detection and Prediction of Stuck-Pipe Events in Oil & Gas Drilling Operations.”** 2021.
11. **“Machine Learning Algorithm for Prediction of Stuck Pipe Incidents Using Statistical Data: Case Study in Middle East Oil Fields.”** 2021/2022. [Paper](https://link.springer.com/article/10.1007/s13202-021-01436-3)
12. **Abbas et al. “Intelligent Prediction of Stuck Pipe Remediation Using Machine Learning Algorithms.”** SPE ATCE, 2019.
13. **“Stuck Pipe Early Detection on Extended-Reach Wells Using Ensemble Method of Machine Learning.”** SPE 206516-MS, 2021.
14. **“Stuck Pipe Prediction from Rare Events in Oil Drilling Operations.”** Rare-event/HMM precursor study.
15. **“Formation Pressure Prediction and Kick Detection for Offshore Drilling.”** 2024 preprint/dataset study. [Paper](https://arxiv.org/pdf/2409.19724.pdf)
16. **“Event Detection in Drilling Remarks Using Natural Language Processing.”** IADC/SPE 208779-MS, 2022. DOI: [10.2118/208779-MS](https://doi.org/10.2118/208779-MS).
17. **“Sequence Mining and Pattern Analysis in Drilling Reports.”** 2017/2018. [Paper](https://arxiv.org/html/1712.01476v1)
18. **“Machine Learning and Natural Language Processing for Automated Analysis of Drilling and Completion Data.”** 2018.
19. **“PetroBERT: A Domain Adaptation Language Model for Oil and Gas Applications in Portuguese.”** Springer, 2022. [DOI](https://dl.acm.org/doi/10.1007/978-3-030-98305-5_10)
20. **“Statistical and Machine Learning Methods Help Us Identify Analogous Wells for Enhanced Type Well Construction.”** URTeC 3722580, 2022/2023. [DOI](https://doi.org/10.15530/urtec-2022-3722580)

### Patent reading

Read the Landmark patent families on automated offset ranking, NLP-derived risk features, trajectory similarity and offset-trained risk models alongside the papers because they are close to several NWIS system-level claims:

- [WO2021040780A1](https://patents.google.com/patent/WO2021040780A1/en)
- [US20240151134A1](https://patents.google.com/patent/US20240151134A1/en)
- [US20220026596A1](https://patents.google.com/patent/US20220026596A1/en)

## Q. Additional Search Keywords

- `"offset well" AND drilling risk AND similarity`
- `"analog well selection" AND trajectory`
- `"offset well analysis" AND natural language processing`
- `"daily drilling report" AND event extraction`
- `"daily mud report" AND losses AND influx`
- `"drilling report" AND root cause extraction`
- `"non productive time" AND NLP AND drilling`
- `"formation relative depth" AND well correlation`
- `"dynamic time warping" AND well similarity`
- `"cross-well transfer learning" AND drilling`
- `"leave-one-well-out" AND drilling machine learning`
- `"lost circulation" AND uncertainty quantification`
- `"kick detection" AND temporal convolutional network`
- `"stuck pipe precursor" AND Transformer`
- `"torque drag anomaly" AND real time`
- `"pore pressure" AND physics informed machine learning`
- `"cementing failure" AND machine learning`
- `"drilling time series" AND foundation model`
- `"multimodal drilling" AND text AND sensor`
- `"drilling knowledge graph"`
- `"petroleum engineering" AND GraphRAG`
- `"drilling copilot" AND RAG`
- `"engineering document intelligence" AND well completion report`
- `"WITSML" AND knowledge graph`
- `"OSDU" AND drilling analytics`
- `"agentic AI" AND drilling operations`
- `"digital twin" AND offset wells AND drilling`
- `"explainable AI" AND drilling risk`
- `"calibrated early warning" AND drilling`
- `"depth-triggered alert" AND offset well`

## Final Recommendation

Use **Volve as the multimodal backbone, Utah FORGE for reproducible drilling analytics, released Diskos/NLOG/NSTA records for geospatial and document diversity, and OSDU-compatible identifiers for integration**. Measure the project contribution through evidence retrieval, offset-ranking quality, cross-well generalization, warning lead time and provenance—not through the use of an LLM alone.
