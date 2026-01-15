import streamlit as st
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

# 1. Configuración inicial
# Carga variables de entorno si estamos en local
load_dotenv()

# Título de la Práctica
st.set_page_config(page_title="Práctica 3 - Exam AI", page_icon="🎓")
st.title("🎓 Sistema de Examen Asistido por IA")

# 2. Configuración de la IA (Groq)
# Intentamos obtener la clave de los secretos de Streamlit (Nube) o del archivo .env (Local)
api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")

if not api_key:
    st.error("⚠️ No se ha encontrado la API Key de Groq. Configúrala en los Secrets.")
    st.stop()

# Inicializamos el modelo (Llama 3 70B es rápido y potente)
llm = ChatGroq(
    groq_api_key=api_key, 
    model_name="llama3-70b-8192", 
    temperature=0.3
)

# 3. Interfaz de prueba (Simulando el Agente Tutor)
st.subheader("Prueba de Conexión: Agente Tutor")
user_input = st.text_input("Escribe una duda sobre programación:")

if st.button("Consultar al Tutor"):
    if user_input:
        with st.spinner("El tutor está pensando..."):
            # Definimos el rol del sistema (System Prompt)
            messages = [
                SystemMessage(content="Eres un profesor socrático. No des la respuesta directa, ayuda al alumno a pensar."),
                HumanMessage(content=user_input),
            ]
            
            # Llamada a la IA
            response = llm.invoke(messages)
            
            # Mostrar respuesta
            st.success("Respuesta del Tutor:")
            st.write(response.content)
    else:
        st.warning("Por favor, escribe algo antes de enviar.")