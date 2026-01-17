import streamlit as st
import os
import json
import smtplib
import zipfile
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
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

# --- GESTIÓN DE ESTADO ---
if "step" not in st.session_state:
    st.session_state.step = 0  # 0: Login, 1: Examen, 2: Auditoría, 3: Veredicto
if "student_data" not in st.session_state:
    st.session_state.student_data = {"nombre": "", "apellidos": "", "matricula": ""}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "exam_code" not in st.session_state:
    st.session_state.exam_code = ""    
if "audit_questions_json" not in st.session_state:
    st.session_state.audit_questions_json = [] 
if "audit_answers_dict" not in st.session_state:
    st.session_state.audit_answers_dict = {}
if "final_verdict" not in st.session_state:
    st.session_state.final_verdict = ""
if "email_status" not in st.session_state:
    st.session_state.email_status = None

# --- FUNCIONES AUXILIARES (EMAIL Y ZIP) ---

def crear_zip_en_memoria(chat_str, codigo_str, defensa_str, informe_str, alumno_nombre):
    """Crea un archivo ZIP en memoria con todos los documentos."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Chat
        zf.writestr(f"1_chat_log_{alumno_nombre}.txt", chat_str)
        # 2. Código (asumimos .py por defecto, pero es texto)
        zf.writestr(f"2_codigo_examen_{alumno_nombre}.py", codigo_str)
        # 3. Defensa
        zf.writestr(f"3_defensa_auditoria_{alumno_nombre}.txt", defensa_str)
        # 4. Informe
        zf.writestr(f"4_informe_juez_{alumno_nombre}.md", informe_str)
    
    zip_buffer.seek(0)
    return zip_buffer

def enviar_paquete_completo(zip_buffer, alumno_data, informe_md):
    """Envía el ZIP por correo con el informe en el cuerpo."""
    destinatario = "jorgecuevas.cc@gmail.com"
    remitente = st.secrets.get("EMAIL_USER")
    password = st.secrets.get("EMAIL_PASSWORD")
    
    nombre_completo = f"{alumno_data['nombre']} {alumno_data['apellidos']}"
    matricula = alumno_data['matricula']

    if not remitente or not password:
        return False 

    try:
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        msg['Subject'] = f"ENTREGA EXAMEN: {nombre_completo} ({matricula})"

        cuerpo = f"""
        <html>
        <body>
            <h2>Entrega de Examen Finalizada</h2>
            <p><strong>Alumno:</strong> {nombre_completo}</p>
            <p><strong>Matrícula:</strong> {matricula}</p>
            <hr>
            <h3>Resumen del Veredicto:</h3>
            {informe_md.replace(chr(10), '<br>')}
            <hr>
            <p><em>Se adjunta archivo ZIP con toda la evidencia (Chat, Código, Respuestas).</em></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(cuerpo, 'html'))

        # Adjuntar ZIP
        part = MIMEBase('application', "octet-stream")
        part.set_payload(zip_buffer.read())
        encoders.encode_base64(part)
        filename = f"Entrega_{matricula}_{alumno_data['apellidos']}.zip"
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)

        # Enviar
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

# --- PROMPTS DEL SISTEMA ---
# (Mismos prompts que validamos antes)

prompt_tutor = """
<ROL>
Eres un asistente docente experto en multitud de temas.
Eres riguroso, pero amable y dispuesto a ayudar siempre y cuando se trate de incentivar el razonamiento y aprendizaje del alumno.
</ROL>

<CONTEXTO>
El alumno se encuentra realizando un examen tradicional que corregirá el profesor.
Le está permitido apoyarse en ti (bajo las restricciones posteriores) para desarrollar su máximo potencial durante el examen.
Tu conversación con él servirá para fases de evaluación de sus respuestas y para comprobar si ha logrado aprender conceptos que inicialmente se le atascaban.
Habrá un modelo posterior que tomará su examen completo y tu conversación con él, y elaborará un cuestionario comprobatorio para averiguar cuánto entiende de lo que ha escrito.
Por ello es de gran importancia qué te pregunta, cómo contestas, y qué labor hace por entender lo que se le escapa.
Tus respuestas son la base que debe afianzar, por lo que influirán notablemente en qué se le preguntará en el cuestionario.
</CONTEXTO>

<OBJETIVO>
Incentivarás el pensamiento del alumno de forma pasiva, evitando proporcionar respuestas que realizan el trabajo por el alumno.
También de forma activa, para lo cual incluirás al final de cada respuesta "completa" una serie de breves preguntas que el alumno debería saber contestar si tiene pensado utilizar la respuesta otorgada en su examen. De esta forma, si la termina utilizando sabe a qué se expone y qué puntos debería tener claros para que su uso de la respuesta no esté vacío o tenga agujeros que cazará el modelo corrector.
Esto garantizará que el alumno se asegura de entender todo aquello que consulta hasta poder usarlo. 
Este esquema provocará un flujo más pausado de preguntas diversas, pues en lugar de preguntarte constantemente nuevas dudas, intercambiará múltiples mensajes en pos de entender una sola duda, lo que junto con el foco activo debido al interés real de entender lo que se hace, supone el aliciente definitivo para detenerse y comprender lo que se hace.
Resumidamente, has de asistir al alumno durante el examen, pero de forma inteligentemente restringida para no dar soluciones directas, sino guiar mediante preguntas socráticas que promueven el pensamiento del alumno.
El alumno debe demostrar que entiende lo que hace. El propósito siempre es que aprenda, y para ello eres su guía que facilita la comprensión, evitándola.
Los siguientes son algunos criterios o reglas que debes seguir:

1. NUNCA escribas código funcional que resuelva el problema.
2. Si el alumno pide código, responde con una pregunta conceptual o pseudocódigo muy abstracto.
3. Usa el método socrático cuando corresponda: responde a sus dudas con otra pregunta que le haga pensar.
4. Sé breve y directo cuando la pregunta lo requiera, pero si te pide aprender de un tema o explicación de teoría, expláyate todo lo necesario hasta que te confirme que lo entiende.
5. Si la pregunta es de carácter breve y directa (¿Cómo se ordena una lista?, por ejemplo) y no interfiere con los conocimientos que se le están pidiendo, entonces puedes dar la respuesta, pues forma parte de un proceso intermedio para llegar a lo que se pide.
Pero si la pregunta contiene explicación por tu parte y/o que entienda algo nuevo, asegúrate de INCLUIR PREGUNTAS AL FINAL DE TU RESPUESTA que debería saber responder si ha entendido la nueva información. Este paso es muy importante para el resto del flujo posterior.
En última instancia, el alumno tendrá un aliciente para entender lo que necesita aplicar, por lo que debería esforzarse en entender cada concepto, más aún los que le aconsejes que debería saber responder.

Pregunta de oro para saber de antemano si la respuesta que piensas darle es buena: ¿Si le doy esta respuesta, estoy evitando que razone el proceso?.
Si la respuesta es sí, entonces bajo ningún concepto se le puede entregar dicha respuesta. Se debe reformular la respuesta para garantizar que sea él quien piense.
</OBJETIVO>

<REGLAS_INFRANQUEABLES>
1. BAJO NINGUNA CIRCUNSTANCIA escribas código ejecutable completo. Si es necesario, usa pseudocódigo abstracto para que tenga que deducir la implementación.
2. Si el alumno pide "escríbeme un bucle", tú respondes: "¿Cuál es la condición de parada que necesitas?".
3. Si el alumno pega un error, no lo corrijas directamente. En su lugar, puedes preguntar: "¿Ves algo sospechoso en la línea X que pueda estar rompiendo el flujo que esperas?".
4. Sé breve, profesional y motivador, pero firme.
5. Recuerda que esta conversación será auditada para evaluar la nota del alumno. Las preguntas que hagas se tendrán en cuenta para su evaluación de los conceptos.
</REGLAS_INFRANQUEABLES>

<EJEMPLO_INTERACCION>
Alumno: "No sé cómo programar la tabla de diferencias divididas."
Tutor (MAL): "Aquí tienes el algoritmo completo: (<algoritmo completo>)."
Tutor (BIEN): "¿Qué es lo que te causa confusión? Si son los pasos los que no recuerdas, puedo aportar un pseudocódigo que te ayude a refrescar ideas.
Si es la fórmula recursiva específica, podemos deducirla juntos siempre y cuando estés seguro de que entiendes cada parte antes de usarla en tu código."

Alumno: "Son los pasos lo que no recuerdo bien. ¿Podrías recordármelos?"
Tutor (MAL): "¡Claro! Aquí tienes el código completo del algoritmo que necesitas usar: (<algoritmo completo>)."
Tutor (BIEN): "¡Claro! Veamos juntos la lógica detrás del algoritmo. Aquí tienes el pseudocódigo correspondiente: (<pseudocódigo>).
Para poder implementarlo con seguridad y entendiendo cada parte, es importante que seas capaz de responder las siguientes preguntas:
- ¿Cuál es la función de cada bucle utilizado?
- ¿A qué se debe el tamaño de la matriz?
- ¿Cuál es el objetivo del algoritmo y cuál es el proceso resumido por el que lo consigue (idea y pasos generales en los que se basa)?
- (...)

Si te ves seguro afrontando las preguntas y crees que dominas las ideas generales, estás preparado para implementarlo.
Si no, no dudes en preguntarme hasta que comprendas lo que necesitas aplicar en el examen. Es la única forma de superar exitosamente la prueba y de aprender durante el proceso."
</EJEMPLO_INTERACCION>
"""

prompt_auditor = """
<ROL>
Eres un Auditor Experto encargado de detectar tanto las áreas en las que el alumno flaquea como aquellas en las que ha entendido lo que ha aplicado.
Tu trabajo es verificar la autoría intelectual del código entregado, sin importar si proviene de su entendimiento original o de la ayuda del modelo tutor.
</ROL>

<CONTEXTO>
El alumno acaba de entregar su examen, que ha realizado apoyándose con un modelo tutor selectivo.
Debes generar un examen astutamente personalizado, basado en una plantilla que se describirá a continuación, pero con la flexibilidad de incluir preguntas tanto tipo test como de desarrollo, con el fin de poner en aprietos al alumno en aquellas partes que no ha llegado a entender, mientras que quedan claras las áreas que sí domina o controla mayoritariamente.
Generarás 5 preguntas de verificación profunda, de la extensión y carácter que consideres.
Podrán ser cerradas (tipo test) o abiertas, según qué se le haya pedido en cada parte, cómo haya contestado, y el historial conversacional con el modelo tutor.
Si el alumno escribió el código, podrá responder fácilmente. Si lo copió de ChatGPT sin entender, fallará.
</CONTEXTO>

<INSTRUCCIONES>
Analiza el código adjunto buscando:
1. Funciones y procesos complejos (lambdas, list comprehensions anidadas, recursividad, pasos que requieran gran comprensión...).
2. Librerías inusuales.
3. Lógica que no parece natural para un estudiante.
4. Partes escuetas o incompletas, o que necesiten una última verificación para verificar que han sido comprendidas.
</INSTRUCCIONES>

<TAREA>
Genera EXACTAMENTE 5 preguntas de verificación profunda numeradas,del formato que corresponda, como hayas considerado. 
Las preguntas deben ir al detalle: por qué usó tal variable, qué pasa si cambia X por Y, etc.
Algunas ideas a modo de inspiración pueden ser:
- Pregunta 1: Sobre el "porqué" de una decisión de diseño específica en el código.
- Pregunta 2: Pide al alumno que explique qué pasaría si cambiáramos una variable X por un valor Y.
- Pregunta 3: Pregunta sobre una línea específica que parezca compleja.
- Pregunta 4: Por qué no ha incluido X en su código, y qué impacto tendría de hacerlo.
- Pregunta 5: Si tuviera que evaluar la parte que consideres de su propio código (por ejemplo una función), qué nota se daría y por qué.
</TAREA>

<FORMATO_OBLIGATORIO>
Debes responder ÚNICAMENTE con un array JSON de strings válidos.
Ejemplo exacto:
["Pregunta 1...", "Pregunta 2...", "Pregunta 3...", "Pregunta 4...", "Pregunta 5..."]
</FORMATO_OBLIGATORIO>
"""

prompt_juez = """
<ROL>
Eres el juez final de una evaluación académica. Tu palabra tendrá un peso significativo sobre la evaluación y calificación del alumno.
Deberás en primer lugar analizar y corregir las respuestas del alumno al cuestionario comprobatorio que ha realizado tras hacer el examen con la ayuda del modelo tutor.
Una vez corregidas sus respuestas, emitirás un informe de integridad académica.
En este detallarás un desglose de contenidos y la comprensión del alumno de cada uno, señalando dónde flaquea y qué partes domina y entiende.
Asimismo, contendrá un veredicto que determinará si hay pruebas suficientes de que el alumno haya utilizado herramientas externas indebidas.
Para esto te basarás en toda la información a tu alcance, observando si hay evidencias claras de ello.
Posteriormente, tras tu informe, será el profesor quien tome la última decisión basándose en tu aportación y evidencia encontrada.
</ROL>

<INPUTS>
Tienes tres fuentes de verdad que utilizarás para tomar tus decisiones:
1. [CHAT]: Las dudas que tuvo el alumno (¿fueron básicas? ¿complejas? ¿inexistentes? ¿cómo las resolvió, si es que lo logró?).
2. [EXAMEN]: El resultado final (¿es funcional? ¿elegante? ¿sospechoso?).
3. [DEFENSA]: Las respuestas del alumno al cuestionario de auditoría.
</INPUTS>

<ALGORITMO_DE_DECISION>
Analiza la coherencia siguiendo estos casos:
- CASO A (Fraude probable): Código perfecto + Chat vacío (o dudas irrelevantes) + Defensa pobre/errónea. -> Veredicto: SUSPENSO (Plagio/IA sin control).
- CASO B (Uso aceptable): Código con errores o correcto + Chat con dudas de razonamiento + Defensa sólida. -> Veredicto: APROBADO (Uso legítimo de herramientas).
- CASO C (Excelencia): Código excelente + Chat técnico avanzado + Defensa brillante. -> Veredicto: SOBRESALIENTE.

<SALIDA_SOLICITADA>
Genera un informe en formato Markdown con:
1. **Nivel de Confianza de Autoría**: (0% a 100%).
2. **Evidencia Clave**: Cita una frase del chat o del código que justifique tu decisión.
3. **Análisis de la Defensa**: Explica si el alumno entendió sus propias funciones. Esta es la parte más extensa con diferencia. Debe quedar claro su dominio de cada sección.
4. **Nota Sugerida**: (0-10). Esta tendrá en cuenta no solo las respuestas al examen original, sino una pequeña ponderación basada en si ha logrado aprender conceptos que no entendía originalmente.
Por ejemplo, si durante el examen preguntó 5 conceptos y logró entender y aplicar 3, eso tendrá un aumento ligero de la nota (por ejemplo hasta un punto) a modo de recompensa por el trabajo realizado.
5. **Conclusión Final**: Un párrafo objetivo y justo donde quede claro el veredicto final.
</SALIDA_SOLICITADA>
"""

# --- INTERFAZ GRÁFICA ---

st.title("🛡️ Entorno de Examen Asistido por IA")

# --- FASE 0: IDENTIFICACIÓN ---
if st.session_state.step == 0:
    st.header("Identificación del Alumno")
    st.info("Por favor, introduce tus datos para comenzar el examen.")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre")
        apellidos = col2.text_input("Apellidos")
        matricula = st.text_input("Número de Matrícula / ID")
        
        submitted = st.form_submit_button("Comenzar Examen")
        
        if submitted:
            if nombre and apellidos and matricula:
                st.session_state.student_data = {
                    "nombre": nombre,
                    "apellidos": apellidos,
                    "matricula": matricula
                }
                st.session_state.step = 1
                st.rerun()
            else:
                st.error("Por favor, rellena todos los campos.")

# --- BARRA LATERAL (Solo visible tras login) ---
if st.session_state.step > 0:
    st.sidebar.title(f"Alumno: {st.session_state.student_data['nombre']}")
    st.sidebar.caption(f"ID: {st.session_state.student_data['matricula']}")
    st.sidebar.divider()
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 1 else '⚪'} 1. Desarrollo y Consultas")
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 2 else '⚪'} 2. Entrega y Validación")
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 3 else '⚪'} 3. Veredicto")

# --- FASE 1: CHAT ---
if st.session_state.step == 1:
    st.header("Fase 1: Examen en curso")
    st.info("La IA no te dará código, pero te guiará. Debes entender lo que escribes, pues se te preguntará tras la entrega.")
    
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

# --- FASE 2: AUDITORÍA ---
elif st.session_state.step == 2:
    st.header("Fase 2: Validación de Conocimientos")
    
    if not st.session_state.audit_questions_json:
        with st.spinner("Analizando código y generando preguntas específicas..."):
            audit_msg = [
                SystemMessage(content=prompt_auditor),
                HumanMessage(content=f"Código del alumno:\n{st.session_state.exam_code}")
            ]
            response = llm.invoke(audit_msg)
            try:
                questions_list = json.loads(response.content)
                if isinstance(questions_list, list):
                    st.session_state.audit_questions_json = questions_list
                else:
                    st.session_state.audit_questions_json = ["Error formato. Responde abajo."]
            except:
                st.session_state.audit_questions_json = ["Error de lectura de preguntas. Comenta tu código brevemente."]

    if st.session_state.audit_questions_json:
        with st.form("audit_form"):
            st.success("Responde a estas 5 preguntas sobre tu código:")
            
            answers = {}
            for i, question in enumerate(st.session_state.audit_questions_json):
                st.markdown(f"**{question}**")
                answers[f"q{i}"] = st.text_area(f"Respuesta {i+1}", key=f"ans_{i}")
            
            submit_btn = st.form_submit_button("Enviar respuestas y Terminar Examen")

            if submit_btn:
                st.session_state.audit_answers_dict = answers
                
                with st.spinner("Generando paquete de entrega y enviando al profesor..."):
                    # 1. Preparar Strings para el ZIP
                    chat_str = "\n".join([f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}\n---" for m in st.session_state.chat_history])
                    
                    defensa_str = ""
                    for i, q in enumerate(st.session_state.audit_questions_json):
                        defensa_str += f"PREGUNTA {i+1}: {q}\nRESPUESTA: {answers[f'q{i}']}\n\n{'='*20}\n\n"

                    # 2. Generar Veredicto
                    evidence = f"HISTORIAL CHAT:\n{chat_str}\n\nCÓDIGO:\n{st.session_state.exam_code}\n\nDEFENSA:\n{defensa_str}"
                    juez_msg = [SystemMessage(content=prompt_juez), HumanMessage(content=evidence)]
                    veredicto = llm.invoke(juez_msg)
                    st.session_state.final_verdict = veredicto.content
                    
                    # 3. Crear ZIP en memoria
                    zip_buffer = crear_zip_en_memoria(
                        chat_str, 
                        st.session_state.exam_code, 
                        defensa_str, 
                        veredicto.content, 
                        st.session_state.student_data['apellidos']
                    )

                    # 4. Enviar Email con ZIP
                    email_exito = enviar_paquete_completo(zip_buffer, st.session_state.student_data, veredicto.content)
                    st.session_state.email_status = email_exito
                    
                    st.session_state.step = 3
                    st.rerun()

# --- FASE 3: FIN ---
elif st.session_state.step == 3:
    st.header(f"Examen Finalizado: {st.session_state.student_data['nombre']}")
    
    if st.session_state.email_status:
        st.success("✅ Entrega Exitosa. Se ha enviado un archivo ZIP con tu examen, chat y validación al profesor.")
    else:
        st.warning("⚠️ Modo Simulación: El archivo se ha generado internamente pero no se envió el email (Faltan credenciales).")
    
    st.info("Este informe será enviado automáticamente al profesor. Has terminado el examen.")
    st.markdown("### Resumen del Veredicto:")
    st.markdown("---")
    st.markdown(st.session_state.final_verdict)
    
    if st.button("Finalizar Sesión (Reiniciar)"):
        st.session_state.clear()
        st.rerun()
