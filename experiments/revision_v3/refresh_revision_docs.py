"""Refresh the author handoff after completed evidence/PDF audits; no experiments."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil

ROOT=Path(__file__).resolve().parent

def main():
    audit=json.loads((ROOT/'results/final_evidence_audit.json').read_text())
    assert audit['all_pass']
    current=json.loads((ROOT/'results/current_results.json').read_text())
    assert all(s.get('finished') and not s.get('last_error') for s in current['status'].values())
    for name in ('CHECKPOINT_ACTIVE_IMPROVEMENT_2026-10-30.txt','REVIEWER_CLOSURE_V3_RU.txt'):
        old=ROOT/'source_history'/('before_final_handoff_'+name)
        if not old.exists():shutil.copyfile(ROOT/name,old)
    entries=[
      ('R1.1','Что унаследовано от SLE, статус предшественника',
       'SLE прямо назван внутренним неопубликованным предшественником. Таблица I отделяет state/invariants/steps; виртуальные handles описаны отдельно от физического обновления всех копий. Coupled fault9 показывает необходимость нового template binding.',
       'main II, IV-C/D, VII-C; joint_ablation_runs.jsonl; source_history'),
      ('R1.2 / R2.1','Исправить exposed-key confidentiality',
       'Теорема и весь threat model требуют секретных mask keys и скрытых метаданных. MiMC/PRP и SHAKE simulation разделены. Добавлены switching/truncation/key-collision terms; 128-битное поле не выдается за безусловную составную безопасность.',
       'main III, V; parameters.json; notes/VIRTUAL_EPOCH_PRIVACY_DRAFT.txt'),
      ('R1.3 / R2.4','Retrieval, capacity, exactness и полнота кандидатов',
       'Сформулированы fixed-scan retrieval, validity/dedup, admission rejection и строгий сертификат distance<B с exhaustive fallback. Каждый candidate bit сверяется с отдельным полевым oracle; mixed/no/all и N3 исключают маскировку ошибки fallback. Full scan/fused/polynomial сравниваются полностью.',
       'main IV-A/B, VII-B; private_client_runs.jsonl; private_fused_runs.jsonl'),
      ('R1.E1','Рекомендован полный интегрированный run с ценой масок',
       'Измерены полные query/rekey, old/new masks, checks, selection, shuffle, refresh/write; phase timers и per-party share reload. Новая парная persisted N128 серия:27.80672→12.80256 s и2710.01→589.957 MB.',
       'main VII-D; supplement I-VIII, XVIII-XXI; current_results.json'),
      ('R1.E2 / R2.6','Float/binary utility, selection, pairs, calibration, unknown probes',
       'Идентичные изображения/splits/ties для float/sign.512 calibration+512 unknown identities,20 assignments,128 query identities до N4096. Численная ошибка strict-threshold устранена без refit; каждый cal count<=allowed и все native open/closed flags воспроизведены. Обе SFace512 seeds, paired CI, перенос на оба CelebA cohorts и реальные MPC inputs N8/128 завершены.',
       'main VI-A, VII-A; calibration_precision_audit.json; frontend_confirmation/summary.json'),
      ('R2.2','Польза сверх shared roots и обычного шифрования, позиционирование',
       'Matched shared-root/refresh baseline сохранен. Полный AES-128-CTR control и3 независимых/MPC KAT пройдены. CTR выполняет тот же полезный контракт. Добавленная маскировка относится к C-only exposure при секретных ключах; порог MPC не усиливается. Primary-source сравнение UE/UT/MUSES/HERS/Pura/PFIP/CryptoFace/BioZKFHE отражено в тексте.',
       'main II, VII-D; aes_baseline_summary.json; notes/PRIOR_ART_CONTRACT_TABLE.csv'),
      ('R2.3','Полный system cost, RAM, storage/access hiding',
       'Actual own-share-file lifecycle, несколько rekeys, reload и rollback пройдены. External probe/threshold/pad дают каждому серверу одну degree-two share; открыт только padded result, acceptance отдельно не открыт. Таблица XXI сводит новые rounds/RSS. Fixed public scans, secret complete-row shuffle и all-field refresh описаны. Atomicity ограничена логическим выбором состояния.',
       'main III, IV-C/D, VI-B; supplement III, X, XXI; private_client_protocol.json'),
      ('R2.5','Сильный transition baseline и масштаб >128',
       'Full128-bit compact-sort/merge matched control сохранен, quadratic join исключен из основного сравнения. Реальные LFW roots, N512/N1024,3 пары полных rekey/query: N1024 rekey202.81033→113.1467 s,19389.7→5402.05 MB. Холодный trusted-owner ввод отделен от persisted state. Разброс, wall/VM, rounds/RSS сохранены.',
       'main VI-B, VII-D; supplement IV-VII, XVIII-XXI; lazy_epoch_runs.jsonl'),
      ('R2.A1','PRP, field, keys, MiMC, expansion, security level',
       'Prime2^128-3637247,81 cubic rounds,9 независимых full-field keys,8x64-bit mask words,canonical128-bit decomposition, passive5-party threshold2, statistical80. Исходная слабая key-support конфигурация раскрыта и исключена из текущих timing claims.',
       'main Table II, V; parameters.json; supplement I-II'),
      ('R2.A2','Hardware/network/software/repetitions',
       'Pinned MP-SPDZ commit, Intel i5-1135G7/Windows/WSL, warmups,3/5 repetitions и SD указаны. Завершены16 ячеек RTT0/1/20/50ms по3 измерения, echo medians0.075/2.763/20.828/50.977ms. Это loopback stream-delay emulation, не physical WAN. Queues/CPU/party logs сохранены.',
       'main VI-B, VII-D; supplement VII, XXI-XXII; network_runs.jsonl'),
      ('R2.A3','Сохранить и расширить supplement',
       'Приложение пересобрано:12 страниц, protocols, phase/range/memory/capacity/calibration/transfer/CI/network/resource tables. Frozen и новые серии не смешаны.',
       'output/pdf/supplement.pdf; manuscript_v3/supplement.tex'),
      ('R2.A4','Сократить повторения без раздувания main',
       'Повторы мотивации и first-combination claims убраны; старые timing detail перенесены в supplement. Основной текст9 страниц вместе с references, biographies и photos; все27 страниц3PDF визуально проверены.',
       'output/pdf/main.pdf; results/pdf_visual_qa.json'),
    ]
    matrix={'generated_utc':datetime.now(timezone.utc).isoformat(),'all_numbered_concerns_addressed_in_revision':True,'meaning':'A concrete response and evidence are supplied for every concern; acceptance and independent novelty judgment remain with reviewers.','entries':[{'reviewer_point':a,'concern':b,'completed_response':c,'evidence':d} for a,b,c,d in entries]}
    (ROOT/'results/reviewer_closure_matrix_v3.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['Итоговая карта ответа рецензентам,2026-10-30',
           'TBIOM-2026-08-0274. Все замечания получили конкретный ответ/изменения/проверки.',
           'Это готовность локальной ревизии к авторскому просмотру, а не решение журнала.','']
    for a,b,c,d in entries:lines.extend([a+': '+b,c,'Где проверять: '+d,''])
    lines.extend(['Что действительно улучшено',
      'Смена ключей N128 из сохраненных долей ускорена примерно2.17x, трафик уменьшен4.59x; N512/N1024 подтверждают снижение работы при обновлении.',
      'SFace512 дает97.295%/96.895% Rank1 при N4096 против93.672% FaceNet512. Обе seeds имеют положительный парный CI; CelebA transfer также лучше. Это смена frontend целиком, не новая криптография.',
      'Полный запрос с приватным I/O проверен. Fused5.93s иfullscan5.99s при N128 сопоставимы; polynomial25.10s. Полезного exact index speedup не заявляем.',
      'Численная поправка открыто сохранена: только *_corrected для новых open-set итогов. Повышенный SFace DIR сопровождается повышенным FPIR; равного-FPIR сравнения нет.','',
      'Остаточные научные границы',
      'Самостоятельность системного вклада требует оценки рецензентов. Больше скорости/точности не доказывает first-in-literature novelty.',
      'Passive MPC, assumed PRP, hidden handles/index/labels/tags, local-host timings, logical atomicity. Malicious security, post-compromise guarantees, crash/replay/OS-erasure и production-scale deployment не установлены.',
      'Архив не содержит face images/features/roots/weights/transform arrays/private shares. Старый R1 пакет неизменен. Отправка/публикация не выполнялась.'])
    (ROOT/'REVIEWER_CLOSURE_V3_RU.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    queue={'authoritative_checkpoint':'CHECKPOINT_ACTIVE_IMPROVEMENT_2026-10-30.txt','all_experiment_series_completed':True,'active_processes':[],'sequential_pipeline':[],'remaining_experiments_required_by_current_plan':[],
      'completed':['joint invariant ablation','strong compaction pilots retained','virtual epoch/cold scale N512/N1024','actual persisted shares','AES control and three secure KATs','exact polynomial/vector candidate operator','external shared probe','client-only padded output/fullscan/fused controls','SFace extraction and predefined projection study','strict threshold correction','paired transfer/CIs/actual secure roots both seeds','RTT0/1/20/50 stream emulation','3PDF compilation/all27page visual QA','135-check final evidence audit'],
      'next_human_step':'Author review of article, supplement and response before any journal submission.','not_submitted':True,'archive_audit':'output/package_manifest.json and results/archive_reproduction_audit.json after packaging'}
    (ROOT/'ACTIVE_QUEUE_2026-10-30.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding='utf-8')
    checkpoint=['AUTHORITATIVE COMPLETION CHECKPOINT,2026-10-30',
      'No active experiment/compile jobs. Current intended experimental and revision plan is complete.',
      'Previous changing queue/checkpoint preserved under source_history/before_final_handoff_*.txt.',
      'Current entry points: README_REPRODUCE_V3.txt; REVIEWER_CLOSURE_V3_RU.txt; results/reviewer_closure_matrix_v3.json.',
      'Current evidence: results/current_results.json, final_evidence_audit.json, pdf_visual_qa.json.',
      'PDFs: output/pdf/main.pdf9pages; supplement.pdf12pages; response_to_reviewers.pdf6pages. All current pages visually inspected.',
      'Frozen R1 SHA '+audit['frozen_R1_sha256'],
      'Current document hashes: '+json.dumps(audit['pdfs']),
      'Do not rerun completed MPC, extraction or model fitting unless a new research question/change requires it.',
      'Use only *_corrected V3 open-set outcomes. Original numerical defect/attempts are retained.',
      'MPC drivers/heavy analysis/plot/PDF share runtime/.msle_v3_driver.lock. Do not run old R1 jobs concurrently.',
      'Virtual logical handles remain stable; all shares refresh. All5 parties colocated; RTT experiment is stream-delay emulation.',
      'Private client kernels reveal only pad-masked result; trusted-controller/DIAG roles are outside production corruption/privacy claim.',
      'There is no journal submission/repository push. Final artifact is for author review.',
      'Archive completion is authoritative only when output/package_manifest.json CRC/hash flag and results/archive_reproduction_audit.json are true.']
    (ROOT/'CHECKPOINT_ACTIVE_IMPROVEMENT_2026-10-30.txt').write_text('\n'.join(checkpoint)+'\n')
    prior=ROOT/'notes/PRIOR_ART_AUDIT.json';old=json.loads(prior.read_text())
    old['status']='Historical initial triage; superseded for current claims by PRIOR_ART_2025_2026_UPDATE.txt and PRIOR_ART_CONTRACT_TABLE.csv. Targeted primary-source positioning is complete for this revision; not an exhaustive novelty proof.'
    prior.write_text(json.dumps(old,indent=2))
    print('AUTHOR_HANDOFF_DOCS_REFRESHED; no submission performed')

if __name__=='__main__':main()
