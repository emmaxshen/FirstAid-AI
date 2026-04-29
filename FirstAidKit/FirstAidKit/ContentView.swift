//
//  ContentView.swift
//  FirstAidKit
//
//  Created by Emma Shen on 4/27/26.
//

import SwiftUI
import UIKit
import Vision
import CoreML

struct ContentView: View {
    @State private var cameraOn = false
    @State private var capturedImage: UIImage? // holds UIImage or nil
    @State private var classificationResult: String = ""
    
    var body: some View {
        VStack {
            Button("Start classification!") {
                cameraOn = true
            }
            // modifier: presents full screen when cameraOn == true
            .fullScreenCover(isPresented: $cameraOn) {
                // CameraView takes a pic and returns UIImage 
                CameraView(image: $capturedImage)
            }
            
            // if captured image exists, then show
            if let image = capturedImage {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(height: 200)
                
                Button("Classify Injury") {
                    classifyImage(image)
                }
                .padding()
            }
            
            // Show classification result
            Text(classificationResult)
                .padding()
        }
        .padding()
    }
    
    func classifyImage(_ image: UIImage) {
        // step 1: load mlmodel (trained from createml and exported as coreml) and wrap in Vision's VNCoreMLModel
         guard let model = try? VNCoreMLModel(for: commonWounds(configuration: MLModelConfiguration()).model) else {
             classificationResult = "Failed to load model"
             return
         }
        
        // completion handler: runs after smth completes
            // when classification finishes, handle results by running this code
        // step 2: create VNCoreMLRequest with wrapped model that instructs which model to use + when classification finishes
         let request = VNCoreMLRequest(model: model) { request, error in
             if let error = error {
                 classificationResult = "Classification error: \(error.localizedDescription)"
                 return
             }
             
             // step 4c: read results (called AFTER handler.perform completes)
             guard let results = request.results as? [VNClassificationObservation],
                   let topResult = results.first else {
                 classificationResult = "No results found"
                 return
             }
             
             // VNClassificationObservation has:
             //   .identifier (String): "burn", "cut", etc.
             //   .confidence (Float): 0.0 to 1.0
             classificationResult = "\(topResult.identifier): \(Int(topResult.confidence * 100))% confidence"
         }
        
         // step 3: wrap image as CIImage that vision takes in
         guard let ciImage = CIImage(image: image) else {
             classificationResult = "Failed to convert image"
             return
         }
        
        // executes this request
         let handler = VNImageRequestHandler(ciImage: ciImage, options: [:])
        
         // step 4: handler.perform() does THE HEAVY LIFTING
         do {
             try handler.perform([request])
             // VNImageRequestHandler
                // converts CIImage -> CVPixel Buffer (CoreML input)
                // resizes img to model's expected input size
                // normalizes pixel values
                // sends CVPixelBuffer to CoreML Model
             // CoreML
                // runs inference and returns raw results back to VNImageRequestHandler
                // Vision converts raw to VNClassificationObservation which has label and confidence level format
          
         } catch {
             classificationResult = "Failed to perform classification: \(error.localizedDescription)"
         }
    
    }
}

#Preview {
    ContentView()
}
