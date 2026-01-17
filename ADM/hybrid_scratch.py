#checks if ensemble in metadata
    if metadata:
        if metadata.get('use_ensemble') is not None:
            global_opts['use_ensemble'] = metadata.get('use_ensemble')
        if metadata.get('ensemble_n') is not None:
            global_opts['ensemble_n'] = metadata.get('ensemble_n')
        if metadata.get('ensemble_temp') is not None:
            global_opts['ensemble_temp'] = metadata.get('ensemble_temp')
        if metadata.get('verifier_temp') is not None:
            global_opts['verifier_temp'] = metadata.get('verifier_temp')

    
    #if ensemble runs requested, perform multiple independent samples then verify deterministically
    if global_opts['use_ensemble']:
        samples = []
        for _ in range(int(global_opts['ensemble_n'])):
            try:
                resp = await client.chat.completions.create(**{**base_req, 'temperature': float(global_opts['ensemble_temp'])})
                raw = resp.choices[0].message.content.strip()
            except Exception as e:
                raw = f"[ERROR] {e}"
            ans_i, reas_i, raw_i = await parse_raw(raw)
            samples.append({'answer': str(ans_i).strip(), 'reasoning': reas_i, 'raw': raw_i})

        # majority vote on answer
        answers = [s['answer'] for s in samples]
        if answers:
            most_common = Counter(answers).most_common(1)
            best_answer = most_common[0][0]
        else:
            best_answer = ''

        # pick the most detailed reasoning among samples that match best_answer
        candidates = [s for s in samples if s['answer'] == best_answer]
        if not candidates:
            candidates = samples
        # choose reasoning with maximum length (heuristic)
        chosen = max(candidates, key=lambda s: len(str(s.get('reasoning') or '')))
        candidate_raw = chosen.get('raw', '')
        candidate_reasoning = chosen.get('reasoning', '')

        # verifier pass (deterministic)
        verify_prompt = (
            "You are a deterministic verifier.\n"
            "Assess whether the following reasoning justifies the final answer.\n"
            "If you agree, return JSON with keys 'reasoning' and 'answer' where 'answer' is the same decision.\n"
            "If you disagree, provide corrected reasoning and the corrected 'answer'.\n"
            f"\nCANDIDATE OUTPUT:\n{candidate_raw}\n"
        )

        try:
            vresp = await client.chat.completions.create(**{**base_req, 'messages': [{"role": "user", "content": verify_prompt}], 'temperature': float(global_opts['verifier_temp'])})
            vraw = vresp.choices[0].message.content.strip()
            try:
                vparsed = json.loads(vraw)
                final_answer = str(vparsed.get('answer', best_answer)).strip()
                final_reasoning = vparsed.get('reasoning', candidate_reasoning)
                hidden_reasoning = response.choices[0].message.reasoning_content

                final_raw = vraw
            except Exception:
                # verifier did not return JSON — fallback to candidate
                final_answer = best_answer
                final_reasoning = candidate_reasoning
                final_raw = candidate_raw
        except Exception:
            final_answer = best_answer
            final_reasoning = candidate_reasoning
            final_raw = candidate_raw

        # log the ensemble samples for debugging
        log_to_json(turn_num, question, json.dumps({'ensemble_samples': samples}), final_reasoning, final_answer, model_id, hidden_reasoning, file_path=log_file, metadata=metadata)
        return final_answer, final_reasoning
    
        #use configurable temperatures and ensemble/verifier settings
    global_opts = {
        'use_ensemble': globals().get('USE_ENSEMBLE', False),
        'ensemble_n': globals().get('ENSEMBLE_N', 3),
        'ensemble_temp': globals().get('ENSEMBLE_TEMP', 0.5),
        'verifier_temp': globals().get('VERIFIER_TEMP', 0.0),
    }
    
    
        #allow CLI override of summary question
    global SUMMARY_OVERRIDE_ALLOWED
    if globals().get('SUMMARY_OVERRIDE_ALLOWED', False):
        summary_question = (
            "Based on the session interaction above, what is your final outcome?\n"
            "You may disagree with the answer provided by the inventive step tool if your reasoning justifies it.\n"
            "State a single final decision on whether an inventive step is present: 'Yes' or 'No'."
        )
    else:
        summary_question = (
            "Based on the session interaction above, what was the final outcome?\n"
            "State a single final decision based on whether an inventive step is present: 'Yes' or 'No'."
        )
    
        async def parse_raw(raw):
        try:
            parsed = json.loads(raw)
            return parsed.get('answer', ''), parsed.get('reasoning', ''), raw
        except Exception:
            return raw, raw, raw