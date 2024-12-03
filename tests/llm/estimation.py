from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.llms import OpenAI

# LangChain 설정
llm = OpenAI(model="gpt-3.5-turbo", temperature=0)

# PromptTemplate 생성
prompt_template = PromptTemplate(
    input_variables=["message", "name_list", "user_name"],
    template=("""
    메시지를 분석하고 아래 JSON 형식으로 결과를 반환하세요:
    [{"name": "<이름>", "role": "<역할>"}]
    
    규칙:
    - 이름은 제공된 이름 리스트에서 선택하세요: {name_list}.
    - 역할은 다음 중 하나여야 합니다: 'citizen', 'police', 'mafia', 'doctor'.
    - 메시지에 "나" 또는 1인칭 대명사가 나오면 그것을 {user_name}으로 간주하고 해당 역할을 매핑하세요.
    - 매칭되지 않는 이름이나 역할은 무시하세요.
    
    분석할 메시지: "{message}"
    """)
)

# LLMChain 생성
chain = LLMChain(llm=llm, prompt=prompt_template)

# 입력 값
message = "나는 경찰이고 예린이가 마피아야."
name_list = ["예린", "도윤", "지훈", "민서"]
user_name = "도윤"

# LangChain 실행
result = chain.run({
    "message": message,
    "name_list": ", ".join(name_list),
    "user_name": user_name,
})

print(result)
