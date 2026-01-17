import streamlit as st
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Práctica 3 - Entorno Seguro", page_icon="🛡️", layout="wide")

# Cargar API Key
api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("⚠️ Falta la API Key. Configura los secrets.")
    st.stop()

# Inicializar modelo
llm = ChatGroq(groq_api_key=api_key, model_name="llama-3.3-70b-versatile", temperature=0.3)

# --- FUNCIONES AUXILIARES (EMAIL) ---
def enviar_informe_email(informe_md, alumno_code):
    """
    Envía el informe por correo. 
    Requiere configurar EMAIL_USER y EMAIL_PASSWORD en st.secrets para funcionar realmente.
    """
    destinatario = "jorgecuevas.cc@gmail.com"
    remitente = st.secrets.get("EMAIL_USER")
    password = st.secrets.get("EMAIL_PASSWORD")

    # Si no hay credenciales configuradas, simulamos el envío para no romper la demo
    if not remitente or not password:
        return False # Indica que fue simulado

    try:
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        msg['Subject'] = "REPORT: Informe de Integridad Académica (Práctica 3)"

        cuerpo = f"""
        <html>
        <body>
            <h2>Nuevo Informe Generado</h2>
            <p>Se ha completado una evaluación.</p>
            <hr>
            <h3>Informe del Juez IA:</h3>
            {informe_md.replace(chr(10), '<br>')}
            <hr>
            <p><em>Este correo ha sido generado automáticamente por el sistema Exam AI.</em></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(cuerpo, 'html'))

        # Conexión con Gmail (o el servidor que configures)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

# --- GESTIÓN DE ESTADO ---
if "step" not in st.session_state:
    st.session_state.step = 1  
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "exam_code" not in st.session_state:
    st.session_state.exam_code = ""    
if "audit_questions_json" not in st.session_state: # Cambiado a lista JSON
    st.session_state.audit_questions_json = [] 
if "audit_answers_dict" not in st.session_state:
    st.session_state.audit_answers_dict = {}
if "final_verdict" not in st.session_state:
    st.session_state.final_verdict = ""
if "email_status" not in st.session_state:
    st.session_state.email_status = None

# --- PROMPTS DEL SISTEMA ---

# 1. TUTOR (Sin cambios significativos, mantenemos tu versión lógica)
prompt_tutor = """
<ROL>
Eres un asistente docente experto en multitud de temas.
Eres riguroso, pero amable y dispuesto a ayudar siempre y cuando se trate de incentivar el razonamiento y aprendizaje del alumno.
</ROL>

<CONTEXTO>
El alumno está en un examen. Puede usarte, pero tú no puedes resolverle el examen.
Tus respuestas influirán en el cuestionario de validación posterior.
</CONTEXTO>

<OBJETIVO>
Incentivarás el pensamiento. NO des código funcional completo.
Si el alumno pide código, responde con preguntas conceptuales o pseudocódigo abstracto.
Si explicas algo nuevo, INCLUYE PREGUNTAS AL FINAL que el alumno debería saber responder si ha entendido.
</OBJETIVO>

<REGLAS_INFRANQUEABLES>
1. NUNCA escribas código funcional ejecutable.
2. Usa el método socrático.
3. Si el alumno pega un error, pregúntale qué cree que falla, no se lo arregles.
4. Recuerda que todo esto será auditado.
</REGLAS_INFRANQUEABLES>
"""

# 2. AUDITOR (MODIFICADO PARA JSON Y 5 PREGUNTAS FIJAS)
prompt_auditor = """
<ROL>
Eres un Auditor Experto. Tu trabajo es verificar la autoría intelectual del código.
</ROL>

<TAREA>
Analiza el código y genera EXACTAMENTE 5 preguntas de verificación profunda numeradas.
Las preguntas deben ir al detalle: por qué usó tal variable, qué pasa si cambia X por Y, etc.
</TAREA>

<FORMATO_OBLIGATORIO>
Debes responder ÚNICAMENTE con un array JSON de strings válidos. Sin markdown, sin explicaciones previas.
Ejemplo exacto de salida esperada:
["Pregunta 1: ¿Por qué usaste...?", "Pregunta 2: Explica la función...", "Pregunta 3...", "Pregunta 4...", "Pregunta 5..."]
</FORMATO_OBLIGATORIO>
"""

# 3. JUEZ (Sin cambios en lógica, solo recibe los inputs)
prompt_juez = """
<ROL>
Eres el juez final. Corregirás las respuestas del alumno y emitirás un informe de integridad.
</ROL>

<INPUTS>
1. [CHAT]: Historial de dudas.
2. [EXAMEN]: Código entregado.
3. [DEFENSA]: Preguntas del auditor y respuestas del alumno.
</INPUTS>

<ALGORITMO>
- CASO A (Fraude): Código perfecto + Chat vacío/irrelevante + Defensa pobre. -> SUSPENSO.
- CASO B (Aceptable): Dudas razonables + Defensa sólida. -> APROBADO.
- CASO C (Excelencia): Chat técnico + Defensa brillante. -> SOBRESALIENTE.

<SALIDA>
Genera un informe Markdown con:
1. **Nivel de Confianza de Autoría**: (0-100%).
2. **Evidencia Clave**.
3. **Análisis de la Defensa**: Detallado por pregunta.
4. **Nota Sugerida**: (0-10) con bonus si aprendió durante el chat.
5. **Conclusión Final**: Párrafo de cierre.
</SALIDA>
"""

# --- INTERFAZ GRÁFICA ---

st.title("🛡️ Entorno de Examen Asistido por IA")

st.sidebar.title("Fases del Examen")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 1 else '⚪'} 1. Desarrollo y Consultas")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 2 else '⚪'} 2. Entrega y Validación")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 3 else '⚪'} 3. Veredicto")

# --- FASE 1: CHAT ---
if st.session_state.step == 1:
    st.header("Fase 1: Examen en curso")
    st.info("La IA no te dará código, pero te guiará. Debes entender lo que escribes.")
    
    for msg in st.session_state.chat_history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.write(msg.content)

    user_input = st.chat_input("Duda conceptual...")
    if user_input:
        st.session_state.chat_history.append(HumanMessage(content=user_input))
        with st.chat_message("user"):
            st.write(user_input)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                messages = [SystemMessage(content=prompt_tutor)] + st.session_state.chat_history
                response = llm.invoke(messages)
                st.write(response.content)
                st.session_state.chat_history.append(AIMessage(content=response.content))

    st.divider()
    uploaded_file = st.file_uploader("Sube tu examen (.py o .ipynb)", type=["py", "ipynb", "txt"])
    if uploaded_file and st.button("Entregar y Validar"):
        st.session_state.exam_code = uploaded_file.read().decode("utf-8")
        st.session_state.step = 2
        st.rerun()

# --- FASE 2: AUDITORÍA (5 INPUTS) ---
elif st.session_state.step == 2:
    st.header("Fase 2: Validación de Conocimientos")
    
    # Generar preguntas (JSON) si no existen
    if not st.session_state.audit_questions_json:
        with st.spinner("Analizando código y generando 5 preguntas específicas..."):
            audit_msg = [
                SystemMessage(content=prompt_auditor),
                HumanMessage(content=f"Código del alumno:\n{st.session_state.exam_code}")
            ]
            response = llm.invoke(audit_msg)
            try:
                # Intentamos parsear el JSON que devuelve la IA
                questions_list = json.loads(response.content)
                if isinstance(questions_list, list):
                    st.session_state.audit_questions_json = questions_list
                else:
                    st.error("Error formato IA. Reintentando...")
            except json.JSONDecodeError:
                # Fallback si la IA no devuelve JSON puro (raro con Llama 3)
                st.warning("Formato de respuesta inusual, mostrando texto plano.")
                st.session_state.audit_questions_json = ["Error formato. Responde abajo."]
                st.markdown(response.content)

    # Formulario con los 5 inputs
    if st.session_state.audit_questions_json:
        with st.form("audit_form"):
            st.success("Responde a estas 5 preguntas sobre TU código:")
            
            answers = {}
            for i, question in enumerate(st.session_state.audit_questions_json):
                st.markdown(f"**{question}**")
                answers[f"q{i}"] = st.text_area(f"Respuesta {i+1}", key=f"ans_{i}")
            
            submit_btn = st.form_submit_button("Enviar respuestas y Terminar Examen")

            if submit_btn:
                # 1. Guardar respuestas
                st.session_state.audit_answers_dict = answers
                
                # 2. Generar Veredicto Inmediatamente
                with st.spinner("Enviando respuestas al tribunal y notificando al profesor..."):
                    chat_log = "\n".join([msg.content for msg in st.session_state.chat_history])
                    
                    # Formatear defensa para el juez
                    defensa_str = ""
                    for i, q in enumerate(st.session_state.audit_questions_json):
                        defensa_str += f"PREGUNTA: {q}\nRESPUESTA ALUMNO: {answers[f'q{i}']}\n\n"

                    evidence = f"""
                    HISTORIAL CHAT: {chat_log}
                    CÓDIGO: {st.session_state.exam_code}
                    DEFENSA (PREGUNTAS Y RESPUESTAS):
                    {defensa_str}
                    """
                    
                    juez_msg = [
                        SystemMessage(content=prompt_juez),
                        HumanMessage(content=evidence)
                    ]
                    veredicto = llm.invoke(juez_msg)
                    st.session_state.final_verdict = veredicto.content
                    
                    # 3. Enviar Email
                    email_exito = enviar_informe_email(veredicto.content, st.session_state.exam_code)
                    st.session_state.email_status = email_exito
                    
                    # 4. Cambiar fase
                    st.session_state.step = 3
                    st.rerun()

# --- FASE 3: FIN (AUTOMÁTICA) ---
elif st.session_state.step == 3:
    st.header("Examen Finalizado")
    
    if st.session_state.email_status:
        st.success("✅ El informe ha sido enviado correctamente al email del profesor (jorgecuevas.cc@gmail.com).")
    else:
        st.warning("⚠️ Modo Simulación: El informe se ha generado pero no se envió por email (Faltan credenciales SMTP).")
    
    st.info("Este informe será enviado automáticamente al profesor. Has terminado el examen.")
    
    st.markdown("### Copia para el alumno:")
    st.markdown("---")
    st.markdown(st.session_state.final_verdict)
    
    if st.button("Iniciar Nuevo Alumno (Reiniciar)"):
        st.session_state.clear()
        st.rerun()
