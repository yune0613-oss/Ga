import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
import time

# ==========================================
# 🔑 구글 인공지능 API 설정
# ==========================================
genai.configure(api_key="")
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="🌟 찐! AI 자동 피드백 마법사", layout="wide")

# --- 앱 내장 메모리 (반 관리 템플릿) ---
if 'class_templates' not in st.session_state:
    st.session_state.class_templates = {
        "공통수학1 기본 월금반": "박선규 / 꼼꼼하지만 속도가 약간 느림 / 시간 분배 연습 강조\n박선우 / 심화 문제에 지레 겁을 먹음 / 칭찬과 격려 위주의 상담 선호\n김은성 / 성격이 급해 연산 실수가 잦음 / 오답노트 철저히",
        "중3-1 심화 화목반": "김학생 / 선행이 잘 되어 있음 / 고등 과정 연계 짚어주기\n이학생 / 계산 실수가 잦음 / 반복 훈련 원하심"
    }

# 사이드바: 반 템플릿 관리
with st.sidebar:
    st.header("⚙️ 우리 학원 반 관리")
    new_class_name = st.text_input("반 이름 입력")
    new_class_traits = st.text_area("학생 성향 (이름 / 성향 / 어머님니즈)", height=150)
    if st.button("💾 반 저장하기"):
        if new_class_name.strip():
            st.session_state.class_templates[new_class_name] = new_class_traits
            st.success(f"'{new_class_name}' 저장 완료!")
            
    st.markdown("---")
    if st.session_state.class_templates:
        class_to_delete = st.selectbox("삭제할 반 선택", list(st.session_state.class_templates.keys()))
        if st.button("❌ 선택한 반 삭제"):
            if class_to_delete in st.session_state.class_templates:
                del st.session_state.class_templates[class_to_delete]
                st.rerun()

# --- 메인 화면 ---
st.title("🌟 AI 맞춤형 학원 피드백 마법사")

st.markdown("### 1단계: 학원 프로그램 JSON 데이터 붙여넣기")
json_input = st.text_area("JSON 데이터 입력칸 (문항별 단원 정보)", height=130)

st.markdown("### 2단계: 학생 성적 입력 방식 선택")
input_mode = st.radio("입력 방식을 선택하세요", ["엑셀 파일 업로드 (기존 O/X 방식)", "오답 번호 텍스트 입력 (한글 파일 연동용)"])

uploaded_file = None
sheet_name = None
text_wrong_input = ""

if input_mode == "엑셀 파일 업로드 (기존 O/X 방식)":
    uploaded_file = st.file_uploader("학생 답안 엑셀 파일 선택", type=["xlsx", "xls"])
    if uploaded_file is not None:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = [sheet for sheet in xls.sheet_names if "기본값" not in sheet]
        if sheet_names:
            sheet_name = st.selectbox("📝 피드백을 생성할 회차(시트)를 선택하세요", sheet_names)
else:
    st.markdown("📌 **한글 프로그램/리포트 오답 입력 요령**")
    st.info("형식: `학생이름 : 틀린문제번호, 번호` (예시: `김은성 : 2, 5, 7, 14` / 다 맞았으면 오답 번호 생략 또는 '없음')")
    text_wrong_input = st.text_area("학생별 오답 번호 입력칸", height=150, placeholder="박선우 : 14\n장주하 : 6, 13, 14\n이재윤 : 5, 11, 14, 20")

st.markdown("### 3단계: 피드백을 만들 반 선택")
options = ["직접 입력"] + list(st.session_state.class_templates.keys())
selected_class = st.selectbox("🎯 반을 선택하세요", options)

if selected_class == "직접 입력":
    class_name = st.text_input("새로운 반 이름을 입력하세요")
    default_traits = "이름 / 학생성향 / 어머님성향\n"
else:
    class_name = selected_class
    default_traits = st.session_state.class_templates[selected_class]

traits_input = st.text_area("학생 성향 확인 (수정 가능)", height=130, value=default_traits)

if st.button("🚀 AI가 분석한 완벽한 피드백 생성하기", type="primary"):
    if json_input and (uploaded_file or text_wrong_input) and class_name:
        try:
            with st.spinner("🧠 AI가 학생별 성향과 오답 데이터를 입체적으로 분석 중입니다..."):
                data = json.loads(json_input)
                df_q = pd.DataFrame([
                    {"문항번호": str(p["problem_no"]), "단원명": p["curriculum"]["middle_unit_name"]} 
                    for p in data.get("problems", [])
                ])
                total_q = len(df_q)
                
                traits_dict = {}
                for line in traits_input.strip().split('\n'):
                    if not line.strip() or "이름 / 학생성향" in line: continue
                    parts = [p.strip() for p in line.split('/')]
                    if len(parts) >= 2:
                        traits_dict[parts[0]] = {"student": parts[1], "parent": parts[2] if len(parts)>2 else ""}

                students_list = []
                all_scores = []

                # 1) 엑셀 입력 방식 처리
                if input_mode == "엑셀 파일 업로드 (기존 O/X 방식)" and uploaded_file and sheet_name:
                    df_student_input = pd.read_excel(uploaded_file, sheet_name=sheet_name, skiprows=8)
                    bigo_col = next((col for col in df_student_input.columns if '비고' in str(col)), None)
                    
                    for index, row in df_student_input.iterrows():
                        name = str(row.get('이름', '')).strip()
                        if not name or name in ['계', '평균', 'nan']: continue
                        
                        status = ""
                        if bigo_col and pd.notna(row[bigo_col]):
                            val = str(row[bigo_col]).strip()
                            if any(x in val for x in ['동영상', '결석', '결시']): status = val
                        
                        answers = [str(row[col]).strip().upper() for col in df_student_input.columns if str(col).isdigit()]
                        
                        if status:
                            students_list.append({"학생이름": name, "상태": status, "점수": 0, "wrong_nums": []})
                        else:
                            wrong_nums = []
                            for idx, row_q in df_q.iterrows():
                                if idx < len(answers) and answers[idx] == 'X':
                                    wrong_nums.append(str(row_q["문항번호"]))
                            score = total_q - len(wrong_nums)
                            all_scores.append(score)
                            students_list.append({"학생이름": name, "상태": "", "점수": score, "wrong_nums": wrong_nums})

                # 2) 텍스트/한글 오답 번호 직접 입력 방식 처리
                else:
                    lines = text_wrong_input.strip().split('\n')
                    temp_parsed = []
                    for line in lines:
                        if ":" not in line: continue
                        parts = line.split(":")
                        name = parts[0].strip()
                        w_str = parts[1].strip()
                        
                        wrong_nums = []
                        if w_str and w_str.lower() != '없음':
                            wrong_nums = [w.strip() for w in w_str.replace(" ", "").split(',') if w.strip()]
                        
                        score = total_q - len(wrong_nums)
                        all_scores.append(score)
                        temp_parsed.append({"학생이름": name, "상태": "", "점수": score, "wrong_nums": wrong_nums})
                    students_list = temp_parsed

                all_scores.sort(reverse=True)
                max_score = all_scores[0] if all_scores else 0
                avg_score = round(sum(all_scores)/len(all_scores), 1) if all_scores else 0
                
                final_text_output = f"🌟 {class_name} 오늘의 시험 분석 및 학생별 피드백 🌟\n\n"
                
                for st_row in students_list:
                    name = st_row["학생이름"]
                    status = st_row["상태"]
                    
                    if status:
                        final_text_output += f"[{name} 학생 피드백]\n▶ 결과\n{name} : {status} / {total_q}\n★ 반 최고 : {max_score} / {total_q}\n◇ 반 평균 : {avg_score} / {total_q}\n◇ 점수분포 : {', '.join(map(str, all_scores))}\n" + "-"*50 + "\n\n"
                    else:
                        score = st_row["점수"]
                        wrong_q_nums = st_row["wrong_nums"]
                        s_trait = traits_dict.get(name, {}).get("student", "성실하게 수업에 참여함")
                        p_trait = traits_dict.get(name, {}).get("parent", "꾸준한 지도")
                        
                        report = f"▶ 결과\n{name} : {score} / {total_q}\n★ 반 최고 : {max_score} / {total_q}\n◇ 반 평균 : {avg_score} / {total_q}\n◇ 점수분포 : {', '.join(map(str, all_scores))}\n\n"
                        report += f"● 오답문항 : {', '.join(wrong_q_nums) if wrong_q_nums else '없음'}\n"
                        
                        # 취약 단원 분석
                        chapter_stats = {}
                        for w_num in wrong_q_nums:
                            matched = df_q[df_q["문항번호"] == w_num]
                            if not matched.empty:
                                ch = matched.iloc[0]["단원명"]
                                chapter_stats[ch] = chapter_stats.get(ch, 0) + 1
                                
                        worst_chapter = max(chapter_stats, key=chapter_stats.get) if chapter_stats else "없음"
                        
                        # --- 💡 입체적 인과관계 분석 AI 프롬프트 ---
                        ai_prompt = f"""
                        당신은 학부모 소통에 능숙하고 학생의 심리와 성적을 입체적으로 꿰뚫어 보는 전문 수학 학원 원장쌤입니다. 학부모님께 보낼 피드백 코멘트를 2문단 내외로 작성하세요.
                        
                        [학생 정보]
                        - 이름: {name}
                        - 점수: {score} / {total_q} (반 평균: {avg_score}, 반 최고: {max_score})
                        - 가장 많이 틀린 취약 단원: {worst_chapter}
                        - 오답 문항 번호: {', '.join(wrong_q_nums) if wrong_q_nums else '없음'}
                        - 평소 학생 성향: {s_trait}
                        - 학부모 니즈 및 성향: {p_trait}

                        [필수 작성 규칙 (입체적 분석)]
                        1. 단순한 단원 나열 금지: 단지 "{worst_chapter}을 틀렸다"고 끝내지 말고, 학생의 '평소 성향(예: 성격이 급함, 심화에 겁을 먹음 등)'과 오늘의 오답 결과를 논리적인 인과관계로 엮어서 설명하세요.
                        2. 명확한 개선 방안: 클리닉 시간이나 오답노트 정돈, 시간 분배 등 이 약점을 구체적으로 어떻게 메울 것인지 액션 플랜을 제시하세요.
                        3. 따뜻한 마무리: "이 부분을 꼼꼼히 채워나가면 다음번엔 훨씬 더 좋은 결과가 있을 거라 믿습니다. 가정에서도 많은 격려와 응원 부탁드립니다."라는 뉘앙스로 든든하게 격려하며 마무리하세요.
                        4. 형식: '[선생님 코멘트]' 라는 제목으로 시작하세요.
                        """
                        try:
                            response = model.generate_content(ai_prompt)
                            ai_comment = "\n" + response.text
                            time.sleep(1) 
                        except Exception as e:
                            ai_comment = f"\n[선생님 코멘트]\n어머님, 오늘 {name} 학생은 '{worst_chapter}' 파트에서 아쉬운 부분이 있었습니다. 성향을 반영하여 꼼꼼히 보완하겠습니다."
                            
                        report += ai_comment
                        final_text_output += f"[{name} 학생 피드백]\n{report}\n" + "-"*50 + "\n\n"
                
                st.success("✨ AI 입체 분석이 완료되었습니다! 텍스트 파일을 다운로드하세요.")
                st.download_button(label=f"📥 {class_name}_AI피드백.txt", data=final_text_output, file_name=f"{class_name}_AI피드백.txt", mime="text/plain")
        except Exception as e:
            st.error(f"오류가 발생했습니다. 입력 데이터를 확인해주세요: {e}")
