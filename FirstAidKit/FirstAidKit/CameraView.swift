//
//  Camera.swift
//  FirstAidKit
//
//  Created by Emma Shen on 4/27/26.
//

import SwiftUI
import UIKit

// swiftUI has no built in camera component
// only way to handle camera in OS is through UIKit's UIImagePickerController
// app in SwiftUI so can't use UIKit's view controllers directly
// UIViewControllerRepresentable wraps UIKit controller

struct CameraView: UIViewControllerRepresentable {
    // ContentView owns capturedImage, CameraView is just reading/writing it passed in as image 
    @Binding var image: UIImage? 

    // creates UIKitController
    // COME BACK: context ?, what is delegate
    func makeUIViewController(context: Context) ->  UIImagePickerController {
        // picker == camera (displays camera UI, captures photo, packages result in info, dismissed)
        let picker = UIImagePickerController()
        // interface displayed is the camera
        picker.sourceType = .camera
        // when user confirms photo, picker auto fills in info dict, if cancel then dismiss
        
        // when an event happening, tell coordinator
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ UIViewControllerType: UIImagePickerController, context: Context) {}
        // leave empty, just req for protocol
    
    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate{
        // reference to parent struct
        let parent: CameraView
        
        // no default value for parent so need initializer
        init(parent: CameraView) {
            self.parent = parent
        }
        
        // user takes a photo
            // info: dict that contains photo: metadata
        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            
            // load photo from info dictionary and save in image
            if let image = info[.originalImage] {
                parent.image = image as? UIImage
            }
            picker.dismiss(animated: true)
        }
        
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
        }
    }
}






