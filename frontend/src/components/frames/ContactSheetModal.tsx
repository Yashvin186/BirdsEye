import React from 'react';
import { X, Image as ImageIcon } from 'lucide-react';

interface Props {
  contactSheetUrl: string;
  onClose: () => void;
}

export const ContactSheetModal: React.FC<Props> = ({ contactSheetUrl, onClose }) => {
  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.75)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(4px)'
    }}>
      <div style={{
        width: '90vw',
        maxHeight: '90vh',
        backgroundColor: '#C7CAD1',
        borderRadius: '6px',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
        border: '1px solid var(--border-strong)',
        overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          padding: '14px 20px',
          backgroundColor: '#34383E',
          color: '#F7F8FA',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ImageIcon size={18} color="var(--accent-lime)" />
            <h2 style={{ fontSize: '15px', fontWeight: 700 }}>Preprocessed Keyframes Contact Sheet</h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#F7F8FA', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Image viewport */}
        <div style={{
          flex: 1,
          padding: '20px',
          overflow: 'auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#1F2329'
        }}>
          <img
            src={contactSheetUrl}
            alt="Keyframe Contact Sheet"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              borderRadius: '4px',
              border: '1px solid rgba(255, 255, 255, 0.2)'
            }}
          />
        </div>

        {/* Footer */}
        <div style={{
          padding: '10px 20px',
          backgroundColor: '#AEB3BD',
          display: 'flex',
          justifyContent: 'flex-end'
        }}>
          <button className="btn btn-secondary" onClick={onClose}>
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
};
