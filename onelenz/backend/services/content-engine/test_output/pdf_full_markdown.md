## Machine Learning Competency Calibration Guide

## Table of Contents

| Machine Learning Competency Calibration Guide ............................................................... 1                                    |
|----------------------------------------------------------------------------------------------------------------------------------------------------|
| Introduction ................................................................................................................................. 2   |
| Machine Learning Case Study Qualification ......................................................................... 2                              |
| Custom Model Use Cases ........................................................................................................... 2               |
| ML Ops Use Cases ........................................................................................................................ 3        |
| AI Services Use Cases Example ................................................................................................. 3                  |
| Machine Learning Competency Technical Validation Prep ................................................ 6                                           |
| Resources ...................................................................................................................................... 7 |

## Introduction

This calibration guide is intended for AWS services path partners who have applied or are  interested  in  the  Amazon  Web  Services  (AWS)  Machine  Learning  Competency program.

The calibration guide has case study qualification and a prep guide for the technical validation  audit.  It  helps  partner  improve  application  quality  and  reduce  cycle  time during the technical validation process.

This document serves as a guide for partners to determine if use cases qualify for ML Competency. The bar for ML Competency is continually raised as more partners and public use cases are admitted. The examples in this document do not guarantee that a use case will qualify since the final decision is made by the AWS auditor, but we strive to keep this document up-to-date.

## Machine Learning Case Study Qualification

All  ML  competency  partners  must  be  able  to  demonstrate  the  ability  to  provide bespoke models. Additionally, competency-level partners must also reflect the ability to judge when an AWS AI Services are more appropriate or more cost efficient. If such a use case is chosen for submission, the simple implementation of an AI Service and its basic features does not meet the case study qualification bar.

AI Service use cases submitted for ML Competency must be innovative and exemplary. The  architecture  of  their  implementation  should  serve  as  a  reference  for  several variations of implementation, and should take advantage of the latest features where relevant.

## Custom Model Use Cases

A partner is expected to submit at least one use case where a bespoke ML model was required  to  achieve  the  best  outcome  for  the  customer.  These  use  cases  should demonstrate: 1) proficiency in data analysis, labelling, and data preparation to achieve the best results, 2) in-depth knowledge of how to choose, build, train, and tune the right algorithm, and 3) a future-proof deployment of the ML model using MLOps best practices. Use cases featuring bespoke models can be built on the SageMaker platform (including any components such as Ground Truth, Neo, and A2I), on ECS or EKS, on EC2 instances, or using any other AWS services. Partners are expected to be familiar with all

of  these  deployment  options,  and  to  be  able  to  articulate  the  benefits  of  the architecture chosen for the submitted use case.

## ML Ops Use Cases

All partners are expected to uphold best practices in CI/CD as articulated in Machine Learning Lens. However, if a Partner specializes in DevOps and provides comprehensive ML Ops as a supporting service or Service offering they may qualify. Managed MLflow is one example. Partners are expected to use the latest MLOps features, or to be able to articulate the benefits of their chosen architecture.

## AI Services Use Cases Example

## Comprehend &amp; Comprehend Medical

- [Sufficient] Integrating Comprehend with multiple AWS services, e.g. Amazon Lex, Transcribe, Textract, Connect, Lambda, QuickSight etc, where Comprehend plays  the  main  role.  The  functionality  of  the  system  should  be  more  than  a simple 'out -of-thebox' API call. E.g. providing real -time sentiment analysis in incoming messages and visualizing aggregated sentiment heat maps. Training for custom entities and/or text classification.
- [Sufficient]  Example:  De-identify  medical  images  with  the  help  of  Amazon Comprehend Medical and Amazon Rekognition
- [Insufficient]  Simple API calls to Comprehend where results are populating a database. No result visualization and broad integration with other AWS services.

## Forecast

- [Sufficient]  Applying  Forecast  to  an  unexpected  or  innovative  use  case, especially in combination with other AWS ML services. A complex combination of different Forecast algorithms, utilizing the strength of each algorithm and combining  the  results.  Building  a  system  which  makes  automated  decisions based  on  the  forecasting  results.  A  reusable,  automated  MLOps  pipeline  for monitoring, re-training, and deploying of new predictors using Step Functions, Airflow, or other orchestration tools.
- [Insufficient] A Forecast solution for predicting sales or other common use cases. Using  autoML  to  choose  the  best  algorithm.  Limited  preprocessing  or  postprocessing of the data, perhaps requiring manual steps or analysis. Integrating

Forecast into your application using APIs, such that users can query and display forecasts to make decisions.

## Fraud Detector

- [Sufficient] 1/ A complete end-to-end fraud detection application, integrated with  other  AWS  services,  like  API  Gateway,  Lambda,  Kinesis  Firehose  and QuickSight for dashboard visualizations. Implementation of an automated way of  measuring  model  performance,  and  using  MLOps  for  periodical  retraining with new data. 2/ A new unconventional application of Fraud Detector: e.g. as an outlier detector for other services, like intelligent call routing for Amazon Connect.
- [Insufficient ]  A  simple  'out -of-thebox'  Fraud  Detector  system,  trained  with customer's  data,  and  deployed  for  real -time  prediction.  No  integration  with other services or model retraining practices.

## Kendra

- [Sufficient] A complicated application where Kendra is part of a larger ecosystem of services, e.g. combining Amazon Kendra, Amazon Comprehend Medical and Amazon Neptune Graph DB for knowledge discovery in medical documents with interactive Knowledge Graphs.
- [Insufficient]  A  simple  static  implementation  of  Kendra  with  a  fixed  set  of documents.

## Lex

- [Sufficient] A complex chatbot with a large number of intents and slots (~&gt; 20), perhaps  split  into  multiple  chatbots  orchestrated  together.  Integrating  with multiple AWS  services to add  advanced  functionality (Connect, Kendra, Transcribe, Textract, Personalize, Rekognition, etc.). Building a custom chatbot UI to add functionality which is not available built-in (date picker, color picker, file uploader, carousel).
- [Insufficient] A Lex chatbot with a small number of intents and slots (~&lt; 20). Using Lambda functions to implement verification and fulfillment. Integrating with third-party communication tools.

## Personalize

- [Sufficient]  Applying  Personalize  for  an  unexpected  or  innovative  use  case, possibly in combination with other AWS ML services. A complex combination of different Personalize solutions, utilizing the strength of each recipe to create a better  result  for  the  customer  (e.g.  combining  results  from  a  HRNN  for

personalized recommendations, with HRNN-Coldstart to include new items, and Personalized-Ranking  applied  on  promotional  items).  A  reusable,  automated MLOps pipeline for monitoring, re-training, canary testing, and deploying of new solutions using Step Functions, Airflow, or other orchestration tools.

- [Insufficient] A Personalize solution for e-commerce recommendations or other common use cases. Using autoML to choose the best recipe. Basic filtering or post-processing  of  the  results.  Deploying  a  couple  of  campaigns  accessed through API calls from your application.

## Polly

- [Sufficient] 1/ Using Polly as a component of an innovative or unusual use case, in  combination  with  other  ML  models  which  demonstrate  advanced  ML knowledge. 2/ Using the advanced options of speech marks, SSML, voice types, and lexicons in combination to meet requirements of a use case. 3/ Creating a custom brand-specific voice.
- [Insufficient] Integrating Polly into your application, using built-in voices and making minimal use of advanced Polly features and controls.

## Rekognition

- [Sufficient]  An  end-to-end image/video analysis application utilizing multiple functionalities  of  Rekognition  (e.g.  face  detection,  demographics  estimation, face  verification).  Integration  with  other  AWS  services  (like  API  Gateway, Lambda, Step Functions, QuickSight, DynamoDB etc), into a complex architecture. Aggregating outputs from Rekognition into informative visualizations, such as floor heat maps, persons of interest etc.
- [Sufficient]  Example:  Improving  fraud  prevention  in  financial  institutions  by building a liveness detection architecture
- [Insufficient] A simple API call to only 1 Rekognition functionality. Integration only with S3. Results just populated into a database. No visualizations.

## Textract

- [Sufficient]  Building  custom  Augmented  AI  workflows  to  review  Textract features which are not built-in. Implementing a text parser and feature extractor that  detects  text  from  a  PDF  document  or  a  scanned  image  of  a  printed document to extract lines of text, using Text Detection API. Optionally using the Document Analysis API to extract tables and forms from the scanned document.
- [Sufficient] Example: Building an end-to-end intelligent document processing solution using AWS

- [Insufficient] Applying Textract to process a batch of documents manually or only partially automated through a pipeline. Setting up Textract with Augmented AI built-in functionality for reviewing key-value pairs.

## Transcribe &amp; Transcribe Medical

- [Sufficient] Using the pre-trained Transcribe models as part of an innovative use case or as part of a large platform combining several ML technologies to achieve a  goal.  Combining results from multiple Transcribe passes with large custom vocabularies  and  custom  language  models.  Applying  complex  pre-processing and post-processing to improve transcription or extract additional information (e.g.  using  Comprehend  syntax  analysis  or  entity  recognition).  Developing custom models to add functionality (e.g. language detection).
- [Insufficient]  Using  the  pre-trained  Transcribe  models,  both  streaming  and batch,  with  little  to  no  customization.  Applying  simple  pre-processing  to improve audio quality before using Transcribe, and simple post-processing to improve  the  quality  of  transcription  (e.g.  spelling  corrections).  Using  a  small custom vocabulary or a small custom language model to improve results.

## Translate

- [Sufficient] Translate needs to be a component of an innovative ML platform using other ML services and models.
- [Sufficient] Example: How SF Medic Provides Real-Time Clinical Decision Support Using AWS Machine Learning Services
- [Insufficient] Translate on its own does not qualify.

## Machine Learning Competency Technical Validation Prep

First,  you  need  to  make  sure  all  pre-requisites  in  the  ML  competency  checklist  ML Competency (Technology), ML Competency (Consulting) are met. It is critical to fill out the technical validation checklist as thoroughly and in-depth as possible on each line, the information the partner provides is what AWS PSAs use to evaluate whether the solution qualifies for AWS ML Competency program requirements.

The reference architecture should be included with this application. This architecture should show all stages of the solution, not only the ones that utilize AWS, and

especially the stages including a machine learning model/algorithm usage. Incomplete information or lack of data will lead to delays in evaluating partner's applications. Once the checklist is completed and accepted, the next step is the technical validation audit ('deep dive').

The technical deep dive is a call between the Partner's technical member(s) and the AWS PSA to discuss how the Partner uses their solution in their submitted public use case scenarios to ensure they meet the AWS ML Competency bar.

This call will be approximately 4 hours and we will review how the solution works, the decisions made when creating/maintaining/updating the solution, trade-offs in those decisions and other checklist requirements. The partner should also conduct the ML Lens review on their solution, and be prepared to answer questions pertaining to the outcomes of this review. Please make sure to have technical SMEs who can speak to the submitted case study in details present at this audit call.

Once the partner has finished the technical deep dive and graduated into our competency program, they are eligible to receive the benefits AWS offers our Machine Learning Competency partners such as Market Development Funds, Priority ranking in AWS search tools, A partner badge, highlighting your now validated Machine Learning specialization and others.  See details in AWS Competency, Service Delivery Program Benefits Guide

## Resources

- Visit  AWS  Specialization  Program  Guide  to  get  overview  of  the  competency program.
- Explore AWS Specialization Program Benefits to understand partner benefits.
- Visit How to build a microsite , How to Build a Customer Case Study
- Check  out  How  to  build  an  architecture  diagram  to  build  an  architecture diagrams.
- Learn about Well Architected Framework on ML Lens review
- AWS Machine Learning Competency Validation Checklist (Technology)
- AWS Machine Learning Competency Validation Checklist (Consulting)