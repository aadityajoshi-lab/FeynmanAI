# Provenance — Feynman Learning Runtime Thesis

**Prepared:** 19 July 2026  
**Method:** primary research, official product documentation, official Indian education/regulatory sources, and local repository inspection. Strategic conclusions are marked as inference in the main brief.

| Source | Source type | Used to support | Verification note |
|---|---|---|---|
| [PNAS: Generative AI without guardrails can harm learning](https://doi.org/10.1073/pnas.2422633122) | Peer-reviewed randomized controlled trial | Generic, unguarded GenAI can undermine unassisted learning | Direct DOI; claim limited to the study’s setting and title/result |
| [Ma et al. 2014 ITS meta-analysis](https://eric.ed.gov/?id=EJ1049508) | Peer-reviewed meta-analysis record | Structured intelligent tutoring can improve achievement vs several comparison conditions | ERIC abstract reports 107 effect sizes and 14,321 participants; not treated as proof for LLM tutoring |
| [Karpicke & Roediger](https://doi.org/10.1126/science.1152408) | Peer-reviewed experimental study | Retrieval practice is part of the proposed active learning loop | Direct journal DOI |
| [OECD digital technologies and learning review](https://www.oecd.org/en/publications/the-impact-of-digital-technologies-on-students-learning_9997e7b3-en.html) | Multisource policy literature review | Technology access alone is insufficient; pedagogy matters | Official OECD publication, 2025 |
| [OpenAI Study Mode](https://help.openai.com/en/articles/11780217) | Official product documentation | General study chat already offers Socratic guidance, uploads, and personalization | Used for competitive baseline only |
| [Google NotebookLM](https://support.google.com/notebooklm/answer/17003757?hl=en) | Official product documentation | Source-grounded notebook capabilities already exist | Used for competitive baseline only |
| [Khanmigo](https://www.khanmigo.ai/) | Official product documentation | Guided, curriculum-coupled AI tutoring exists | Used for competitive baseline only |
| [Duolingo Max](https://blog.duolingo.com/duolingo-max/) | Official product documentation | Constrained path + authored AI roleplay is a strong vertical product primitive | Used for competitive baseline only |
| [MIT 6.S081](https://pdos.csail.mit.edu/6.S081/2021/overview.html) | Official university course material | OS requires runnable systems/labs, not explanations alone | Current course page updated in 2025 |
| [MIT DSP](https://ocw.mit.edu/courses/res-6-008-digital-signal-processing-spring-2011/) | Official university course material | DSP learning combines theory, demonstrations, and problem-solving | Official OpenCourseWare course page |
| [India Ministry of Education AISHE release](https://www.education.gov.in/sites/upload_files/mhrd/files/PIB1999713.pdf) | Official government release | India higher-education enrolment scale | Latest published AISHE figure cited is 2021–22; do not extrapolate it as a current total |
| [AICTE Internship Portal](https://internship.aicte-india.org/index.php/Internshala.php) | Official government platform | India’s learning-by-doing and verified-opportunity ecosystem | Used as ecosystem context, not a market-size claim |
| [UGC Academic Bank of Credits regulations](https://www.ugc.gov.in/e-book/UGC_Regulation/files/basic-html/page556.html) | Official regulation | Feynman must not claim to issue official academic credits | Direct UGC regulation page |
| [WHO AI for health guidance](https://www.who.int/publications/i/item/9789240029200) | Official global health guidance | Medical-learning safety boundary and human accountability | Used for education-versus-clinical boundary |
| [NMC undergraduate curriculum](https://www.nmc.org.in/information-desk/for-colleges/ug-curriculum/1000/) | Official Indian curriculum | Indian medical education is competency-based | Does not imply Feynman can independently certify clinicians |
| [SEBI investment-advisor guidance](https://investor.sebi.gov.in/investment_advisor.html) | Official Indian regulatory guidance | Financial-learning boundary versus personalized investment advice | Used to avoid treating educational content as regulated advice |

## Local repository evidence

The thesis was mapped against the current checkout at `E:\newOpenAI\openX-hackathon`:

- `backend/teachback/models.py` contains `SubjectPack`, `Module`, `Concept`, `LearnerProfile`, `SkillEvidence`, `LearnerMemory`, `LearningAttempt`, `AttemptCheckpoint`, and source-grounded notebook models.
- `frontend/src/components/NotebookWorkspace.tsx` already provides Sources, Chat, Studio artifacts, source citation, notes, and durable notebook context.
- `README.md` identifies the current complete DSAP pack as Sampling and Aliasing and describes a whiteboard/prediction/teach-back workspace.

These local observations support the implementation mapping only; they are not external market or learning-science evidence.
